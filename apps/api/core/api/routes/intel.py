# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Maritime intelligence API routes.

GET  /api/v1/intel                   All events GeoJSON (filterable)
GET  /api/v1/intel/stats             Event counts by type/severity
GET  /api/v1/intel/ngo               NGO/coastguard vessel positions (GeoJSON)
GET  /api/v1/intel/ais-spikes        AIS anomaly events only
POST /api/v1/intel/extract-image     Extract GPS coords from an image URL
POST /api/v1/intel/auto-drift        Trigger SAR drift from a geolocated event
WS   /ws/intel                       Real-time event stream (JSON per event)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.intel.ngo_registry import NGO_VESSELS, get_ngo_info, is_ngo
from core.intel.store import intel_store

router = APIRouter()
logger = logging.getLogger(__name__)


# ── REST endpoints ─────────────────────────────────────────────────────────────

@router.get("/api/v1/intel")
async def get_intel(
    severity: Optional[str] = Query(None, description="critical|high|medium|low"),
    type_filter: Optional[str] = Query(None, alias="type",
                                        description="twitter|news|iom_incident|ais_spike|ngo_activity"),
    limit: int = Query(200, ge=1, le=500),
):
    """
    All intelligence events as GeoJSON FeatureCollection.
    Only events with known coordinates are included in `features`.
    Events without coordinates are listed in `meta.no_coords`.
    """
    all_events = intel_store.events(severity=severity, type_filter=type_filter, limit=limit)
    with_coords = [e for e in all_events if e.lat is not None and e.lon is not None]
    no_coords   = [e for e in all_events if e.lat is None or e.lon is None]

    return {
        "type": "FeatureCollection",
        "features": [e.to_geojson_feature() for e in with_coords],
        "meta": {
            "total": len(all_events),
            "with_coords": len(with_coords),
            "no_coords_count": len(no_coords),
            "no_coords": [
                {"id": e.id, "type": e.type, "severity": e.severity,
                 "title": e.title[:100], "source": e.source,
                 "timestamp_utc": e.timestamp_utc}
                for e in no_coords[:30]
            ],
        },
    }


@router.get("/api/v1/intel/stats")
async def get_intel_stats():
    """Event counts by type and severity."""
    return intel_store.stats()


@router.get("/api/v1/intel/ngo")
async def get_ngo_positions():
    """
    Live positions of known NGO and coastguard vessels from AIS registry.
    Enriched with org, role, and website data.
    Returns GeoJSON FeatureCollection.
    """
    from core.vessels.registry import registry  # lazy to avoid circular

    geojson = registry.get_geojson()
    ngo_features = []
    seen_mmsi: set[str] = set()

    # Enrich positioned NGO vessels from live AIS
    for feat in geojson.get("features", []):
        props = feat.get("properties") or {}
        mmsi = str(props.get("mmsi", ""))
        if not is_ngo(mmsi):
            continue
        info = get_ngo_info(mmsi) or {}
        seen_mmsi.add(mmsi)
        ngo_features.append({
            **feat,
            "properties": {
                **props,
                "intel_type": "ngo_vessel",
                "org": info.get("org", ""),
                "role": info.get("role", ""),
                "vessel_class": "ngo",
            },
        })

    # Add known NGO vessels not currently in AIS (show as "last known" or "offline")
    for mmsi, info in NGO_VESSELS.items():
        if mmsi in seen_mmsi:
            continue
        ngo_features.append({
            "type": "Feature",
            "geometry": None,  # no current position
            "properties": {
                "mmsi": mmsi,
                "ship_name": info.get("name", ""),
                "org": info.get("org", ""),
                "role": info.get("role", ""),
                "flag": info.get("flag", ""),
                "intel_type": "ngo_vessel",
                "ais_status": "offline",
                "vessel_class": "ngo",
            },
        })

    return {
        "type": "FeatureCollection",
        "features": ngo_features,
        "meta": {
            "total_registered": len(NGO_VESSELS),
            "live_ais": len(seen_mmsi),
            "offline": len(NGO_VESSELS) - len(seen_mmsi),
        },
    }


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
async def extract_image_coords(body: ImageExtractRequest):
    """
    Fetch an image URL and extract GPS coordinates.
    Pipeline: EXIF metadata → Claude Vision (claude-haiku-4-5).
    Returns {lat, lon, method, confidence} or 404 if nothing found.
    """
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
                     persons: Optional[int], vessel_type: Optional[str]) -> None:
    """Background: compute drift from an intel event's position."""
    import uuid
    from datetime import datetime, timezone

    from core.db.store import complete_drift_job, create_drift_job, fail_drift_job
    from core.drift.engine import DriftEngine

    job_id = str(uuid.uuid4())
    time_utc = datetime.now(timezone.utc)
    create_drift_job(
        job_id,
        event_id=f"intel:{event_id}",
        lat=lat, lon=lon, domain="ocean_sar",
        duration_h=24,
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
            duration_h=24, domain="ocean_sar", config=cfg,
        )
        complete_drift_job(
            job_id, event_id=f"intel:{event_id}",
            lat=lat, lon=lon, domain="ocean_sar", result=result,
        )
        intel_store.broadcast_event_update(event_id, {"drift_job_id": job_id, "drift_status": "completed"})
        logger.info("Auto-drift completed for intel event %s → job %s", event_id, job_id)
    except Exception as exc:
        fail_drift_job(job_id, event_id=f"intel:{event_id}",
                       lat=lat, lon=lon, domain="ocean_sar", error_message=str(exc))
        logger.warning("Auto-drift failed for intel event %s: %s", event_id, exc)


@router.post("/api/v1/intel/auto-drift")
async def intel_auto_drift(body: AutoDriftRequest):
    """
    Trigger a SAR drift simulation from an intel event's known position.
    The drift runs in a daemon thread so the response returns immediately.
    """
    import threading
    threading.Thread(
        target=_run_intel_drift,
        args=(body.intel_event_id, body.lat, body.lon, body.persons, body.vessel_type),
        daemon=True,
    ).start()
    return {"status": "queued", "intel_event_id": body.intel_event_id}


# ── WebSocket real-time stream ─────────────────────────────────────────────────

@router.websocket("/ws/intel")
async def ws_intel(websocket: WebSocket):
    """
    Real-time intel stream.  Sends a JSON payload for every new IntelEvent
    as it arrives.  Client receives GeoJSON Feature objects.

    On connect: sends the last 50 events as a batch (type="snapshot").
    Then: individual events streamed as type="event".
    """
    await websocket.accept()
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
