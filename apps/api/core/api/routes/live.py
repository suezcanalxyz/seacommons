# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public, privacy-preserving projection of SeaCommons live signals."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from core.config import config
from core.intel.store import intel_store
from core.live.feed import public_drift_collection, public_signal_collection
from core.live.projection import _public_intel_feature

router = APIRouter(prefix="/api/v1/live", tags=["live"])


@router.get("/signals")
async def live_signals(
    limit: int = Query(300, ge=1, le=500),
    days: int = Query(30, ge=1, le=365),
    since: Optional[str] = Query(None),
):
    """Public map-ready signal feed. No private inbound content is returned."""
    return public_signal_collection(limit=limit, days=days, since=since)


@router.get("/signals/{event_id}/response")
async def live_signal_response(event_id: str, request: Request):
    """
    On-demand NGO cross-check for a single live episode.

    Returns which known SAR NGO / coastguard vessels are within range and
    heading toward the episode (bearing/ETA/heading), when each track was last
    saved to the AIS registry, recent motion flags (speed spike, search
    pattern, sudden stop, loitering, rescue cluster — reused from the AIS
    spike detector's stored observations), and other live signals nearby
    (cross-check). Also returns a GeoJSON FeatureCollection (`geojson`) of the
    episode→vessel lines and vessel points for direct map rendering.

    Privacy: only public AIS telemetry and the already-public signal metadata
    are returned — never raw messages or identifiers. Anonymous + rate limited
    like the other live read endpoints.
    """
    from core.api.ratelimit import rate_limit
    from core.intel.ngo_response import analyze_ngo_response

    rate_limit(request, max_per_minute=30, scope="live-response")
    normalized = event_id.removeprefix("intel:")
    event = intel_store.get(normalized)
    if event is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    if event.lat is None or event.lon is None:
        raise HTTPException(status_code=422, detail="Signal has no position")
    if _public_intel_feature(event) is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    related_signals = [
        other
        for other in intel_store.events(limit=300, max_age_days=3)
        if _public_intel_feature(other) is not None
    ]
    try:
        return analyze_ngo_response(event, related_signals=related_signals)
    except ValueError:
        raise HTTPException(status_code=422, detail="Signal has no position")


@router.get("/drifts")
async def live_drifts(limit: int = Query(100, ge=1, le=200)):
    """Public map-ready drift products, kept separate from received signals."""
    return public_drift_collection(limit=limit)


@router.get("/archives")
async def live_archives(limit: int = Query(40, ge=1, le=200)):
    """Anonymised incident index for the Play archive timeline.

    Two kinds of archived incident carry a computed drift: SAR cases opened
    through /api/v1/alert, and OSINT distress events (Alarm Phone, ...) whose
    auto-drift completed. Both are surfaced here, newest first, with only the
    coarse fields Play needs — never the source message or any identifier.
    """
    from core.db.models import DriftResultDB, IntelEventDB
    from core.db.session import session_scope
    from core.db.store import list_alerts

    seen: set[str] = set()
    archives: list[dict] = []

    for alert in list_alerts(limit=limit * 3):
        if alert.get("status") != "completed":
            continue
        event = alert.get("event") or {}
        archives.append({
            "id": alert["event_id"],
            "timestamp": event.get("timestamp"),
            "lat": event.get("lat"),
            "lon": event.get("lon"),
            "vessel_type": event.get("vessel_type") or "case",
            "persons": event.get("persons") or 1,
            "kind": "sar_case",
        })
        seen.add(alert["event_id"])

    try:
        with session_scope() as db:
            rows = (
                db.query(DriftResultDB, IntelEventDB)
                .join(IntelEventDB, IntelEventDB.id == DriftResultDB.event_id)
                .filter(DriftResultDB.status == "completed")
                .filter(IntelEventDB.lat.isnot(None))
                .order_by(IntelEventDB.timestamp_utc.desc())
                .limit(limit * 3)
                .all()
            )
            for drift, ev in rows:
                if ev.id in seen:
                    continue
                meta = ev.meta or {}
                if not (meta.get("is_distress") or ev.type in {"distress", "vessel_incident"}):
                    continue
                archives.append({
                    "id": ev.id,
                    "timestamp": ev.timestamp_utc,
                    "lat": ev.lat,
                    "lon": ev.lon,
                    "vessel_type": meta.get("vessel_type") or "rubber_boat",
                    "persons": meta.get("persons") or meta.get("people") or 1,
                    "kind": "osint_distress",
                })
                seen.add(ev.id)
    except Exception:  # pragma: no cover - archive listing is best-effort
        pass

    archives.sort(key=lambda a: str(a.get("timestamp") or ""), reverse=True)
    return {
        "archives": archives[:limit],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/archives/{event_id}/geojson")
async def live_archive_geojson(event_id: str):
    """Derived geometry for a public Play archive; no source message or identity."""
    from fastapi import HTTPException

    from core.db.store import get_alert, get_drift

    alert = get_alert(event_id)
    drift = get_drift(event_id)
    alert_ok = alert is not None and alert.get("status") == "completed"
    drift_ok = bool(drift) and drift.get("status") == "completed"
    # An OSINT distress archive has a completed drift but no alert row.
    if not drift_ok or (alert is not None and not alert_ok):
        raise HTTPException(status_code=404, detail="Archive not found")
    features = [
        feature
        for feature in (
            drift.get("trajectory"),
            drift.get("cone_6h"),
            drift.get("cone_12h"),
            drift.get("cone_24h"),
        )
        if feature
    ]
    features.extend((drift.get("impact_point") or {}).get("features", []))
    return {"type": "FeatureCollection", "features": features}


@router.get("/sources")
async def live_sources():
    """Public health summary without credentials, endpoint URLs or raw errors."""
    from core.intel.source_registry import source_registry

    registry_sources = {
        source["name"]: source
        for source in source_registry.get_all()
        if source["name"]
        in {
            "X / Twitter",
            "X / Twitter (twikit)",
            "Mastodon",
            "Official NGO RSS",
            "GDACS",
            "Bluesky",
        }
    }
    try:
        from core.connectors.service import status_counts
        from core.db.session import session_scope

        with session_scope() as db:
            whatsapp_connectors = status_counts(db, "whatsapp_cloud")
    except Exception:
        whatsapp_connectors = {}
    whatsapp_ready = bool(
        config.META_APP_ID
        and config.META_APP_SECRET
        and config.META_WEBHOOK_VERIFY_TOKEN
        and whatsapp_connectors.get("active", 0)
    )
    expected = (
        ("X / Twitter (twikit)", "twitter", bool(config.TWIKIT_ENABLED)),
        ("X / Twitter", "twitter", bool(config.TWITTER_BEARER_TOKEN)),
        ("WhatsApp partner intake", "whatsapp", whatsapp_ready),
        (
            "Telegram intake",
            "telegram",
            bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_WEBHOOK_SECRET),
        ),
        ("Partner webhook", "partner", bool(config.PARTNER_WEBHOOK_SECRET)),
    )
    sources = []
    for name, source_type, configured in expected:
        observed = registry_sources.pop(name, None)
        sources.append(
            {
                "name": name,
                "type": source_type,
                "status": observed["status"]
                if observed
                else ("pending" if configured else "offline"),
                "last_poll_at": observed["last_poll_at"] if observed else None,
                "events_last_hour": observed["events_last_hour"] if observed else 0,
                "total_events": observed["total_events"] if observed else 0,
                "consecutive_errors": observed["consecutive_errors"] if observed else 0,
            }
        )
    for observed in registry_sources.values():
        sources.append(
            {
                "name": observed["name"],
                "type": observed["type"],
                "status": observed["status"],
                "last_poll_at": observed["last_poll_at"],
                "events_last_hour": observed["events_last_hour"],
                "total_events": observed["total_events"],
                "consecutive_errors": observed["consecutive_errors"],
            }
        )
    active = sum(1 for source in sources if source["status"] == "active")
    return {
        "sources": sources,
        "summary": {
            "total": len(sources),
            "active": active,
            "degraded": sum(1 for source in sources if source["status"] == "degraded"),
            "offline": sum(1 for source in sources if source["status"] == "offline"),
        },
        "channels": {
            "twitter": bool(config.TWITTER_BEARER_TOKEN),
            "twitter_alarm_phone": any(
                source["name"] == "X / Twitter (twikit)" and source["status"] == "active"
                for source in sources
            ),
            "whatsapp": whatsapp_ready,
            "whatsapp_active_connectors": whatsapp_connectors.get("active", 0),
            "telegram": bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_WEBHOOK_SECRET),
            "partner_webhook": bool(config.PARTNER_WEBHOOK_SECRET),
        },
        "collector": {
            "mode": "continuous",
            "browser_independent": True,
            "persistence": "database",
            "supervisor": "systemd",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ngo-vessels")
async def live_ngo_vessels():
    """Public projection of known SAR NGO/coastguard vessel positions.

    Same data and query as the authenticated operator route
    (/api/v1/intel/ngo) — these vessels already broadcast AIS publicly, so
    there is nothing to withhold; this just gives the public Live map a
    route under the same public /api/v1/live/ prefix as everything else it
    reads, instead of poking a hole in /api/v1/intel's auth gate.
    """
    from core.intel.ngo_registry import ngo_vessel_geojson

    return ngo_vessel_geojson()


@router.get("/platforms")
async def live_platforms():
    """Public projection of Mediterranean oil/gas platform positions
    (static public data — EMODnet/OGA/OSM). Mirrors /api/v1/zones/platforms,
    which is already unauthenticated, under the public Live namespace."""
    from core.api.routes.zones import get_platforms

    return await get_platforms()


@router.websocket("/stream")
async def live_stream(websocket: WebSocket):
    """Public WebSocket snapshot stream; the browser falls back to REST polling."""
    await websocket.accept()
    previous_digest = ""
    try:
        while True:
            snapshot = public_signal_collection(limit=500, days=30)
            payload = json.dumps(
                {
                    "type": "snapshot",
                    "features": snapshot["features"],
                    "meta": snapshot["meta"],
                },
                separators=(",", ":"),
            )
            digest = hashlib.blake2s(payload.encode(), digest_size=8).hexdigest()
            if digest != previous_digest:
                await websocket.send_text(payload)
                previous_digest = digest
            else:
                await websocket.send_text('{"type":"ping"}')
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
