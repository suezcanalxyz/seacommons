# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public, privacy-preserving projection of SeaCommons live signals."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from core.config import config
from core.intel.store import IntelEvent, intel_store

router = APIRouter(prefix="/api/v1/live", tags=["live"])

_PUBLIC_INTEL_TYPES = frozenset(
    {"distress", "twitter", "mastodon", "news", "iom_incident", "ais_spike", "ngo_activity"}
)
_PUBLIC_METADATA = frozenset(
    {
        "category",
        "country",
        "dead",
        "drift_job_id",
        "drift_status",
        "incident_id",
        "is_distress",
        "missing",
        "platform",
        "region",
    }
)


def _safe_public_url(value: str) -> str:
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    return value if parsed.scheme in {"http", "https"} and bool(parsed.netloc) else ""


def _public_intel_feature(event: IntelEvent) -> Optional[dict[str, Any]]:
    """Convert an internal event to the stable public signal contract."""
    publication = str(event.metadata.get("publication_status") or "").lower()
    if event.type not in _PUBLIC_INTEL_TYPES and publication != "published":
        return None
    if event.lat is None or event.lon is None:
        return None

    metadata = {key: event.metadata[key] for key in _PUBLIC_METADATA if key in event.metadata}
    return {
        "type": "Feature",
        "id": f"intel:{event.id}",
        "geometry": {"type": "Point", "coordinates": [event.lon, event.lat]},
        "properties": {
            "schema": "org.seacommons.live-signal/v1",
            "id": f"intel:{event.id}",
            "type": event.type,
            "kind": "distress" if event.tier() == "operational" else "context",
            "severity": event.severity or "low",
            "tier": event.tier(),
            "priority": event.priority(),
            "verification_status": event.verification_status(),
            "publication_status": "published",
            "drift_ready": event.tier() == "operational",
            "title": (event.title or "Maritime signal")[:255],
            # Public Live deliberately excludes raw text and author identifiers.
            "text": "",
            "url": _safe_public_url(event.url),
            "source": (event.source or event.type or "public feed")[:64],
            "timestamp_utc": event.timestamp_utc,
            **metadata,
        },
    }


def _published_ingested_features(limit: int) -> list[dict[str, Any]]:
    """
    Project user/partner signals only after an explicit publication decision.

    WhatsApp, SMS and Telegram are private by default. Their raw text, sender
    identifier and provider delivery identifiers never enter this response.
    """
    try:
        from sqlalchemy import select

        from core.db.models import IngestedSignalDB
        from core.db.session import session_scope

        with session_scope() as db:
            rows = list(
                db.execute(
                    select(IngestedSignalDB)
                    .order_by(IngestedSignalDB.received_at.desc())
                    .limit(min(limit * 3, 500))
                ).scalars()
            )
    except Exception:
        return []

    features: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row.payload or {})
        if payload.get("publication_status") != "published":
            continue
        lat, lon = payload.get("lat"), payload.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        signal_id = str(payload.get("signal_id") or row.signal_id)
        condition = str(payload.get("vessel_condition") or "reported distress").replace("_", " ")
        features.append(
            {
                "type": "Feature",
                "id": f"signal:{signal_id}",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "schema": "org.seacommons.live-signal/v1",
                    "id": f"signal:{signal_id}",
                    "type": "distress",
                    "kind": "distress",
                    "severity": "high" if payload.get("medical_emergency") else "medium",
                    "tier": "operational",
                    "priority": 1,
                    "verification_status": "user_reported",
                    "publication_status": "published",
                    "drift_ready": True,
                    "title": f"Maritime signal · {condition}"[:255],
                    "text": "",
                    "url": "",
                    "source": "community report",
                    "timestamp_utc": payload.get("event_time_utc")
                    or payload.get("timestamp_utc")
                    or row.received_at.replace(tzinfo=timezone.utc).isoformat(),
                },
            }
        )
        if len(features) >= limit:
            break
    return features


def public_signal_collection(
    *,
    limit: int = 300,
    days: int = 30,
    since: Optional[str] = None,
) -> dict[str, Any]:
    events = intel_store.events(limit=min(limit * 2, 600), max_age_days=days)
    features = [feature for event in events if (feature := _public_intel_feature(event))]
    features.extend(_published_ingested_features(limit))
    if since:
        features = [
            feature
            for feature in features
            if str(feature["properties"].get("timestamp_utc") or "") > since
        ]
    features.sort(key=lambda f: str(f["properties"].get("timestamp_utc") or ""), reverse=True)
    features.sort(key=lambda f: int(f["properties"].get("priority", 99)))
    features = features[:limit]

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "schema": "org.seacommons.live-feed/v1",
            "total": len(features),
            "with_coords": len(features),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "privacy": "published signals only; private identifiers and raw messages excluded",
        },
    }


@router.get("/signals")
async def live_signals(
    limit: int = Query(300, ge=1, le=500),
    days: int = Query(30, ge=1, le=365),
    since: Optional[str] = Query(None),
):
    """Public map-ready signal feed. No private inbound content is returned."""
    return public_signal_collection(limit=limit, days=days, since=since)


@router.get("/sources")
async def live_sources():
    """Public health summary without credentials, endpoint URLs or raw errors."""
    from core.intel.source_registry import source_registry
    from core.vessels.aisstream import get_client
    from core.vessels.registry import registry

    sources = [
        {
            "name": source["name"],
            "type": source["type"],
            "status": source["status"],
            "last_poll_at": source["last_poll_at"],
            "events_last_hour": source["events_last_hour"],
            "total_events": source["total_events"],
            "consecutive_errors": source["consecutive_errors"],
        }
        for source in source_registry.get_all()
    ]
    ais_client = get_client()
    sources.insert(
        0,
        {
            "name": "AIS",
            "type": "ais",
            "status": "active" if ais_client and ais_client.connected else "offline",
            "last_poll_at": None,
            "events_last_hour": 0,
            "total_events": int(ais_client.messages_received) if ais_client else 0,
            "consecutive_errors": 0 if ais_client and ais_client.connected else 1,
        },
    )
    active = sum(1 for source in sources if source["status"] == "active")
    return {
        "sources": sources,
        "summary": {
            "total": len(sources),
            "active": active,
            "degraded": sum(1 for source in sources if source["status"] == "degraded"),
            "offline": sum(1 for source in sources if source["status"] == "offline"),
            "vessels": registry.stats(),
        },
        "channels": {
            "whatsapp": bool(config.TWILIO_AUTH_TOKEN),
            "telegram": bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_WEBHOOK_SECRET),
            "partner_webhook": bool(config.PARTNER_WEBHOOK_SECRET),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.websocket("/stream")
async def live_stream(websocket: WebSocket):
    """Public WebSocket snapshot stream; the browser falls back to REST polling."""
    await websocket.accept()
    previous_digest = ""
    try:
        while True:
            snapshot = public_signal_collection(limit=300, days=30)
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
