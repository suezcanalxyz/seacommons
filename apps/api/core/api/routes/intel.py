# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Maritime intelligence API routes.

GET  /api/v1/intel                   All events GeoJSON (filterable)
GET  /api/v1/intel/stats             Event counts by type/severity
GET  /api/v1/intel/sources           OSINT source health (registry)
GET  /api/v1/intel/ngo               NGO/coastguard vessel positions (GeoJSON)
GET  /api/v1/intel/ais-spikes        AIS anomaly events only
POST /api/v1/intel/extract-image     Extract GPS coords from an image URL
POST /api/v1/intel/auto-drift        Trigger SAR drift from a geolocated event
POST /api/v1/intel/manual            Manually inject an intel event
WS   /ws/intel                       Real-time event stream (JSON per event)
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.api.ratelimit import acquire_drift_slot, rate_limit, release_drift_slot
from core.intel.store import IntelEvent, intel_store

router = APIRouter()
logger = logging.getLogger(__name__)


# ── REST endpoints ─────────────────────────────────────────────────────────────

@router.get("/api/v1/intel")
async def get_intel(
    severity: Optional[str] = Query(None, description="critical|high|medium|low"),
    type_filter: Optional[str] = Query(None, alias="type",
                                        description="twitter|news|iom_incident|ais_spike|ngo_activity"),
    tier: Optional[str] = Query(None, description="operational|news|signal"),
    limit: int = Query(200, ge=1, le=500),
    days: int = Query(30, ge=1, le=365, description="Only return events from the last N days"),
):
    """
    All intelligence events as a GeoJSON FeatureCollection, **sorted by
    operational priority** (distress first). Events without coordinates are
    returned as features with `geometry: null` so the dashboard can still
    surface them (e.g. an Alarm Phone distress call with no lat/lon yet) —
    the map layer simply skips null-geometry features.
    """
    from datetime import datetime, timezone

    all_events = intel_store.events(severity=severity, type_filter=type_filter, limit=limit, max_age_days=days)
    if tier:
        all_events = [e for e in all_events if e.tier() == tier]

    # Two stable passes: newest-first, then by operational priority. Python's
    # sort is stable, so within one priority the newest event stays on top.
    all_events.sort(key=lambda e: e.timestamp_utc or "", reverse=True)
    all_events.sort(key=lambda e: e.priority())

    with_coords = [e for e in all_events if e.lat is not None and e.lon is not None]
    operational = [e for e in all_events if e.tier() == "operational"]

    return {
        "type": "FeatureCollection",
        "features": [e.to_geojson_feature() for e in all_events],
        "meta": {
            "total": len(all_events),
            "with_coords": len(with_coords),
            "no_coords_count": len(all_events) - len(with_coords),
            "operational_count": len(operational),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/api/v1/intel/stats")
async def get_intel_stats():
    """Event counts by type and severity."""
    return intel_store.stats()


@router.get("/api/v1/intel/sources")
async def get_intel_sources():
    """OSINT source health: last poll time, events/h, error count per monitor."""
    from core.intel.source_registry import source_registry
    sources = source_registry.get_all()
    active   = sum(1 for s in sources if s["status"] == "active")
    degraded = sum(1 for s in sources if s["status"] == "degraded")
    offline  = sum(1 for s in sources if s["status"] == "offline")
    return {
        "sources": sources,
        "summary": {
            "total": len(sources),
            "active": active,
            "degraded": degraded,
            "offline": offline,
        },
    }


@router.get("/api/v1/intel/ngo")
async def get_ngo_positions():
    """
    Live positions of known NGO and coastguard vessels from AIS registry.
    Enriched with org, role, and website data.
    Returns GeoJSON FeatureCollection.
    """
    from core.intel.ngo_registry import ngo_vessel_geojson

    return ngo_vessel_geojson()


@router.get("/api/v1/intel/ais-spikes")
async def get_ais_spikes(limit: int = Query(50, ge=1, le=200)):
    """AIS anomaly events (sudden stops, clusters, NGO search patterns)."""
    events = intel_store.events(type_filter="ais_spike", limit=limit)
    features = [e.to_geojson_feature() for e in events if e.lat is not None]
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {"count": len(features)},
    }


@router.get("/api/v1/intel/twitter")
async def get_twitter_events(
    severity: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=300),
):
    """Social media (Twitter/X) distress signals only."""
    events = intel_store.events(severity=severity, type_filter="twitter", limit=limit)
    features = [e.to_geojson_feature() for e in events if e.lat is not None]
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "count": len(features),
            "no_coords": len(events) - len(features),
        },
    }


@router.get("/api/v1/intel/incidents")
async def get_iom_incidents(limit: int = Query(50, ge=1, le=200)):
    """IOM Missing Migrants verified incidents."""
    events = intel_store.events(type_filter="iom_incident", limit=limit)
    features = [e.to_geojson_feature() for e in events if e.lat is not None]
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {"count": len(features)},
    }


@router.get("/api/v1/intel/archive")
async def get_intel_archive(
    days: int = Query(7, ge=1, le=90, description="How many days back to query"),
    severity: Optional[str] = Query(None),
    type_filter: Optional[str] = Query(None, alias="type"),
    limit: int = Query(500, ge=1, le=2000),
    fmt: str = Query("geojson", description="geojson | json"),
):
    """
    Historical intel events from DB (survives backend restarts).
    Use fmt=json for a flat list; fmt=geojson for map-compatible output.
    """
    from datetime import datetime, timezone, timedelta
    from core.db.session import session_scope
    from core.db.models import IntelEventDB

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        with session_scope() as db:
            q = db.query(IntelEventDB).filter(IntelEventDB.timestamp_utc >= cutoff)
            if severity:
                q = q.filter(IntelEventDB.severity == severity)
            if type_filter:
                q = q.filter(IntelEventDB.type == type_filter)
            rows = q.order_by(IntelEventDB.timestamp_utc.desc()).limit(limit).all()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {exc}")

    if fmt == "json":
        return {
            "events": [
                {
                    "id": r.id, "timestamp_utc": r.timestamp_utc,
                    "type": r.type, "severity": r.severity,
                    "lat": r.lat, "lon": r.lon,
                    "title": r.title, "source": r.source,
                    "url": r.url, "meta": r.meta or {},
                }
                for r in rows
            ],
            "meta": {"count": len(rows), "days": days},
        }

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]} if r.lat and r.lon else None,
            "properties": {
                "id": r.id, "type": r.type, "severity": r.severity,
                "title": r.title, "source": r.source, "url": r.url,
                "timestamp_utc": r.timestamp_utc, **(r.meta or {}),
            },
        }
        for r in rows
    ]
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {"count": len(features), "days": days},
    }


# ── Manual intel event injection ─────────────────────────────────────────────

class ManualIntelRequest(BaseModel):
    title: str
    text: str = ""
    source: str = "manual"
    severity: str = "medium"           # critical | high | medium | low
    type: str = "manual"               # manual | distress | news | twitter | ...
    lat: Optional[float] = None
    lon: Optional[float] = None
    url: str = ""
    linked_mmsi: str = ""


@router.post("/api/v1/intel/manual", status_code=201)
async def inject_manual_intel(body: ManualIntelRequest, request: Request):
    """
    Manually inject an intel event — e.g. from a phone call or direct contact.
    The event is stored in DB and broadcast to all WebSocket clients.
    """
    rate_limit(request, max_per_minute=10, scope="intel-manual")
    from core.intel.source_registry import source_registry
    source_registry.register("Manual", "manual")

    if body.severity not in ("critical", "high", "medium", "low"):
        raise HTTPException(status_code=422, detail="severity must be critical|high|medium|low")

    event = IntelEvent(
        type=body.type,
        severity=body.severity,
        lat=body.lat,
        lon=body.lon,
        title=body.title[:255],
        text=body.text[:1000],
        url=body.url[:511],
        source=body.source or "manual",
        linked_mmsi=body.linked_mmsi,
        metadata={"injected_manually": True},
    )
    stored = intel_store.add(event)
    source_registry.record_poll("Manual", events_found=1 if stored else 0)
    if not stored:
        raise HTTPException(status_code=409, detail="Duplicate event — already in store")
    return {"id": event.id, "timestamp_utc": event.timestamp_utc, "stored": True}


# ── External shared-secret intel ingestion ───────────────────────────────────
# For an operator's own external script/service that produces already-parsed
# text reports (e.g. reading some feed the operator runs independently).
# SeaCommons has no visibility into and makes no claim about how that data
# was produced — this endpoint only accepts a finished {text, url, source}
# report and runs it through the same pipeline (dedup, coordinate
# extraction, triangulation, optional auto-drift) as any other monitor.
# Auth mirrors /api/v1/ingest/webhook: HMAC-SHA256 over the raw body using
# EXTERNAL_INTEL_INGEST_SECRET, not the OIDC operator-role login that
# /api/v1/intel/manual requires — meant for a standalone script, not a human
# in the console.

class ExternalIntelPayload(BaseModel):
    source: str                        # short label for this feed, e.g. "personal-x-relay"
    source_id: str = ""                # upstream ID (e.g. tweet id) for dedup, if known
    text: str
    title: str = ""
    url: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    timestamp_utc: Optional[str] = None
    # Default False: the event still lands in intel_store (visible on the
    # authenticated console, feeds triangulation/auto-drift) but does not
    # appear on the public live.seacommons.org map until the operator
    # explicitly opts an item in — same conservative default as manual
    # console entries, which also don't auto-publish.
    publish: bool = False


@router.post("/api/v1/intel/external", status_code=201)
async def ingest_external_intel(request: Request):
    """Shared-secret ingestion of operator-supplied text reports (see module note above)."""
    import hashlib
    import hmac as hmac_lib

    from core.config import config
    from core.intel.geoextract import (
        classify_severity,
        extract_coords,
        extract_numeric_coords,
        extract_relative_coords,
        is_direct_distress_call,
    )

    expected = config.EXTERNAL_INTEL_INGEST_SECRET
    if not expected:
        raise HTTPException(status_code=503, detail="External intel ingest is not configured")
    raw = await request.body()
    if len(raw) > 20_000:
        raise HTTPException(status_code=413, detail="Payload too large")
    supplied = request.headers.get("x-seacommons-signature", "")
    digest = "sha256=" + hmac_lib.new(expected.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac_lib.compare_digest(supplied, digest):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        body = ExternalIntelPayload.model_validate_json(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid payload") from exc

    rate_limit(request, max_per_minute=60, scope="intel-external")
    from core.intel.source_registry import source_registry

    source_name = f"External / {body.source}"[:64]
    source_registry.register(source_name, "twitter")

    distress = is_direct_distress_call(body.text)
    coords = (
        (body.lat, body.lon) if body.lat is not None and body.lon is not None
        else extract_numeric_coords(body.text) or extract_relative_coords(body.text) or extract_coords(body.text)
    )
    metadata = {
        "is_distress": distress,
        "verification_status": "operator_asserted",
        "coordinate_source": "post_text" if (body.lat is not None or extract_numeric_coords(body.text)) else "place_centroid",
    }
    if body.publish:
        metadata["publication_status"] = "published"
        metadata["source_policy"] = "operator_published"

    event = IntelEvent(
        type="twitter",
        severity=classify_severity(body.text) if distress else "low",
        lat=coords[0] if coords else None,
        lon=coords[1] if coords else None,
        title=(body.title or body.text[:120])[:255],
        text=body.text[:600],
        url=body.url[:511],
        source=source_name,
        timestamp_utc=body.timestamp_utc or "",
        metadata=metadata,
    )
    dedup_key = f"external:{body.source}:{body.source_id}" if body.source_id else ""
    added = intel_store.add(event, dedup_key=dedup_key)
    source_registry.record_poll(source_name, events_found=1 if added else 0)
    if added and distress:
        from core.intel.triangulation import evaluate as evaluate_triangulation
        evaluate_triangulation(event)
    return {"id": event.id, "stored": added, "published": body.publish}


# ── Image coordinate extraction ───────────────────────────────────────────────

class ImageExtractRequest(BaseModel):
    url: str


@router.get("/api/v1/intel/drifts")
async def get_intel_drifts():
    """
    All drift results linked to intel events.
    Returns GeoJSON FeatureCollection with trajectory + cone per event.
    Used by the frontend map layer for persistent auto-drift traces.
    """
    from core.db.store import get_drift
    from core.intel.store import intel_store

    features = []
    for event in intel_store.events(limit=500):
        job_id = event.metadata.get("drift_job_id")
        if not job_id or event.metadata.get("drift_status") != "completed":
            continue
        drift = get_drift(job_id)
        if not drift or drift.get("status") != "completed":
            continue
        for f in [drift.get("trajectory"), drift.get("cone_24h")]:
            if f:
                feat = dict(f)
                props = dict(feat.get("properties") or {})
                props.update({
                    "intel_event_id": event.id,
                    "intel_title": event.title[:80],
                    "intel_source": event.source,
                    "intel_severity": event.severity,
                    "auto_drift": True,
                })
                feat["properties"] = props
                features.append(feat)
        if drift.get("impact_point"):
            for f in drift["impact_point"].get("features", []):
                feat = dict(f)
                props = dict(feat.get("properties") or {})
                props["intel_event_id"] = event.id
                props["auto_drift"] = True
                feat["properties"] = props
                features.append(feat)

    return {"type": "FeatureCollection", "features": features}


@router.post("/api/v1/intel/extract-image")
async def extract_image_coords(body: ImageExtractRequest, request: Request):
    """
    Fetch an image URL and extract GPS coordinates.
    Pipeline: EXIF metadata → Claude Vision (claude-haiku-4-5).
    Returns {lat, lon, method, confidence} or 404 if nothing found.
    """
    rate_limit(request, max_per_minute=10, scope="intel-image")
    from core.intel.vision import extract_from_url

    result = await extract_from_url(body.url)
    if result is None:
        raise HTTPException(status_code=404, detail="No coordinates found in image")
    return result


# ── Auto-drift from intel event ────────────────────────────────────────────────

class AutoDriftRequest(BaseModel):
    intel_event_id: str
    lat: float
    lon: float
    persons: Optional[int] = None
    vessel_type: Optional[str] = "rubber_boat"


def _run_intel_drift(event_id: str, lat: float, lon: float,
                     persons: Optional[int], vessel_type: Optional[str],
                     observed_at: str) -> None:
    """Background: compute drift from an intel event's position."""
    try:
        _run_intel_drift_inner(event_id, lat, lon, persons, vessel_type, observed_at)
    finally:
        release_drift_slot()


def _run_intel_drift_inner(event_id: str, lat: float, lon: float,
                           persons: Optional[int], vessel_type: Optional[str],
                           observed_at: str) -> None:
    import uuid
    import math
    from datetime import datetime, timezone

    from core.db.store import complete_drift_job, create_drift_job, fail_drift_job
    from core.drift.engine import DriftEngine

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    try:
        time_utc = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if time_utc.tzinfo is None:
            time_utc = time_utc.replace(tzinfo=timezone.utc)
        time_utc = min(time_utc.astimezone(timezone.utc), now)
    except (AttributeError, TypeError, ValueError):
        time_utc = now
    elapsed_h = max(0.0, (now - time_utc).total_seconds() / 3600)
    duration_h = min(72, max(24, math.ceil(elapsed_h) + 12))
    create_drift_job(
        job_id,
        event_id=f"intel:{event_id}",
        lat=lat, lon=lon, domain="ocean_sar",
        duration_h=duration_h,
        started_at=time_utc,
    )
    try:
        engine = DriftEngine()
        cfg = {}
        if vessel_type:
            cfg["vessel_type"] = vessel_type
        if persons is not None:
            cfg["persons"] = persons
        result = engine.compute(
            lat=lat, lon=lon, time_utc=time_utc,
            duration_h=duration_h, domain="ocean_sar", config=cfg,
        )
        complete_drift_job(
            job_id, event_id=f"intel:{event_id}",
            lat=lat, lon=lon, domain="ocean_sar", result=result,
        )
        intel_store.update_metadata(event_id, metadata={
            "drift_job_id": job_id,
            "drift_status": "completed",
            "drift_origin_timestamp_utc": time_utc.isoformat(),
            "drift_duration_h": duration_h,
            "drift_completed_at": datetime.now(timezone.utc).isoformat(),
        })
        intel_store.broadcast_event_update(event_id, {"drift_job_id": job_id, "drift_status": "completed"})
        logger.info("Auto-drift completed for intel event %s → job %s", event_id, job_id)
    except Exception as exc:
        fail_drift_job(job_id, event_id=f"intel:{event_id}",
                       lat=lat, lon=lon, domain="ocean_sar", error_message=str(exc))
        intel_store.update_metadata(event_id, metadata={
            "drift_job_id": job_id,
            "drift_status": "failed",
            "drift_error": str(exc)[:240],
        })
        logger.warning("Auto-drift failed for intel event %s: %s", event_id, exc)


def schedule_intel_drift(
    event_id: str,
    lat: float,
    lon: float,
    persons: Optional[int],
    vessel_type: Optional[str],
    observed_at: str,
    *,
    force: bool = False,
) -> bool:
    """Start one durable-linked drift if the shared model slot is available.

    `force` bypasses the once-only guard so a refresher can re-run an
    already-completed drift against freshly observed wind/current forcing —
    the whole point of keeping the drift live as conditions change. It still
    respects the global model slot; a busy engine returns False.
    """
    normalized_id = event_id.removeprefix("intel:")
    event = intel_store.get(normalized_id)
    if event and event.metadata.get("drift_status") in {"computing", "completed"} and not force:
        return True
    if not acquire_drift_slot():
        return False
    intel_store.update_metadata(normalized_id, metadata={
        "drift_status": "computing",
        "drift_requested_at": datetime.now(timezone.utc).isoformat(),
        "drift_origin_timestamp_utc": observed_at,
    })
    try:
        threading.Thread(
            target=_run_intel_drift,
            args=(normalized_id, lat, lon, persons, vessel_type, observed_at),
            daemon=True,
        ).start()
    except Exception:
        release_drift_slot()
        intel_store.update_metadata(normalized_id, metadata={"drift_status": "failed"})
        raise
    return True


@router.post("/api/v1/intel/auto-drift")
async def intel_auto_drift(body: AutoDriftRequest, request: Request):
    """
    Trigger a SAR drift simulation from an intel event's known position.
    The drift runs in a daemon thread so the response returns immediately.

    Public (unauthenticated) endpoint — reachable from the anonymous Live map.
    Protected the same way /api/v1/alert is: a per-IP rate limit plus the
    shared global concurrency semaphore (MAX_CONCURRENT_DRIFTS), so a burst of
    anonymous clicks cannot exhaust CPU/RAM on the pilot VM.
    """
    rate_limit(request, max_per_minute=6, scope="intel-drift")
    normalized_id = body.intel_event_id.removeprefix("intel:")
    stored = intel_store.get(normalized_id)
    lat = stored.lat if stored and stored.lat is not None else body.lat
    lon = stored.lon if stored and stored.lon is not None else body.lon
    observed_at = stored.timestamp_utc if stored else datetime.now(timezone.utc).isoformat()
    if not schedule_intel_drift(
        normalized_id,
        lat,
        lon,
        body.persons,
        body.vessel_type,
        observed_at,
    ):
        raise HTTPException(
            status_code=429,
            detail="Drift engine busy — too many concurrent simulations. Retry shortly.",
            headers={"Retry-After": "30"},
        )
    return {"status": "queued", "intel_event_id": normalized_id, "observed_at": observed_at}


# ── WebSocket real-time stream ─────────────────────────────────────────────────

@router.websocket("/ws/intel")
async def ws_intel(websocket: WebSocket):
    """
    Real-time intel stream.  Sends a JSON payload for every new IntelEvent
    as it arrives.  Client receives GeoJSON Feature objects.

    On connect: sends the last 50 events as a batch (type="snapshot").
    Then: individual events streamed as type="event".
    """
    from core.security import READ_ROLES, authorize_websocket
    protocol = await authorize_websocket(websocket, READ_ROLES)
    if protocol == "closed":
        return
    await websocket.accept(subprotocol=protocol)
    loop = asyncio.get_event_loop()
    intel_store.register_ws(websocket, loop)
    logger.info("Intel WebSocket client connected")

    try:
        # Snapshot of recent events on connect
        recent = intel_store.events(limit=50)
        import json
        snapshot = json.dumps({
            "type": "snapshot",
            "features": [e.to_geojson_feature() for e in recent],
        })
        await websocket.send_text(snapshot)

        # Keep connection alive; new events are pushed via intel_store.broadcast()
        while True:
            await asyncio.sleep(30)
            await websocket.send_text('{"type":"ping"}')

    except WebSocketDisconnect:
        logger.info("Intel WebSocket client disconnected")
    except Exception as exc:
        logger.warning("Intel WebSocket error: %s", exc)
    finally:
        intel_store.unregister_ws(websocket)
