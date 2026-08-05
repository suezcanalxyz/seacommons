# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public, privacy-preserving projection of SeaCommons live signals."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from core.config import config
from core.intel import lifecycle
from core.intel.public_geometry import public_geometry_and_precision
from core.intel.store import IntelEvent, intel_store

router = APIRouter(prefix="/api/v1/live", tags=["live"])

_PUBLIC_INTEL_TYPES = frozenset({"distress", "twitter", "mastodon", "ngo_activity"})
_APPROVED_SOURCE_POLICIES = frozenset(
    {"official_api", "official_rss", "official_site_embed", "trusted_partner"}
)
_BLOCKED_SOURCE_POLICIES = frozenset({"nitter", "scrape", "twscrape", "unofficial"})
_PUBLIC_METADATA = frozenset(
    {
        "category",
        "coordinate_review_status",
        "coordinate_source",
        "country",
        "dead",
        "distress_classification",
        "drift_status",
        "first_source_seen_at",
        "incident_status",
        "incident_id",
        "is_distress",
        "last_source_seen_at",
        "location_uncertainty_m",
        "missing",
        "ocr_attempted",
        "platform",
        "region",
        "source_policy",
        "source_scan_count",
        "repost_count",
        "last_repost_at",
        "area_weather_narrowed",
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
    if event.type == "sar_model" or (event.title or "").strip().lower() == "computed sar drift product":
        # Model outputs belong to Play/Engine, never to the received-signal feed.
        return None
    publication = str(event.metadata.get("publication_status") or "").lower()
    source_policy = str(event.metadata.get("source_policy") or "").lower()
    transport = str(event.metadata.get("via") or event.metadata.get("scrape_source") or "").lower()
    if source_policy in _BLOCKED_SOURCE_POLICIES or any(
        blocked in transport for blocked in _BLOCKED_SOURCE_POLICIES
    ):
        # Old scraper records may still be persisted; they must never re-enter Live.
        return None
    if publication != "published" and source_policy not in _APPROVED_SOURCE_POLICIES:
        return None
    if event.type not in _PUBLIC_INTEL_TYPES and publication != "published":
        return None
    metadata = {key: event.metadata[key] for key in _PUBLIC_METADATA if key in event.metadata}
    # Unlike the event's own `text` (stripped everywhere on public Live,
    # since it may originate from a private WhatsApp/SMS caller who never
    # consented to publication), a thread_reposts `note` only ever comes from
    # the tracked account's OWN public quote/reply to its OWN tweet — already
    # readable by anyone on X. Without it the public "Update" panel would
    # show a link with no indication of what the update actually says, which
    # defeats the point of surfacing it at all.
    thread_reposts = event.metadata.get("thread_reposts")
    if thread_reposts:
        metadata["thread_reposts"] = [
            {"tweet_id": r.get("tweet_id"), "posted_at": r.get("posted_at"),
             "url": r.get("url"), "kind": r.get("kind"), "note": r.get("note")}
            for r in thread_reposts
        ]
    geometry, location_precision = public_geometry_and_precision(event)
    return {
        "type": "Feature",
        "id": f"intel:{event.id}",
        "geometry": geometry,
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
            "source_policy": source_policy or "operator_published",
            "title": (event.title or "Maritime signal")[:255],
            # Public Live deliberately excludes raw text and author identifiers.
            "text": "",
            "url": _safe_public_url(event.url),
            "source": (event.source or event.type or "public feed")[:64],
            "timestamp_utc": event.timestamp_utc,
            "source_timestamp_utc": event.timestamp_utc,
            "received_at": event.metadata.get("first_source_seen_at") or event.timestamp_utc,
            "location_precision": location_precision,
            **metadata,
        },
    }


def _approximate_public_point(signal_id: str, lat: float, lon: float) -> tuple[float, float]:
    """Deterministically displace sensitive inbound coordinates by 0.8-2.5 km."""
    digest = hashlib.blake2s(signal_id.encode(), digest_size=8).digest()
    angle = int.from_bytes(digest[:4], "big") / (2**32) * 2 * math.pi
    radius_m = 800 + int.from_bytes(digest[4:], "big") / (2**32) * 1700
    lat_offset = math.sin(angle) * radius_m / 111_320
    lon_scale = max(0.2, math.cos(math.radians(lat)))
    lon_offset = math.cos(angle) * radius_m / (111_320 * lon_scale)
    return round(lat + lat_offset, 5), round(lon + lon_offset, 5)


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
            rows = [
                {
                    "signal_id": row.signal_id,
                    "source_channel": row.source_channel,
                    "payload": dict(row.payload or {}),
                    "received_at": row.received_at,
                }
                for row in db.execute(
                    select(IngestedSignalDB)
                    .order_by(IngestedSignalDB.received_at.desc())
                    .limit(min(limit * 3, 500))
                ).scalars()
            ]
    except Exception:
        return []

    features: list[dict[str, Any]] = []
    for row in rows:
        payload = row["payload"]
        if payload.get("publication_status") != "published":
            continue
        lat, lon = payload.get("lat"), payload.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        signal_id = str(payload.get("signal_id") or row["signal_id"])
        public_lat, public_lon = _approximate_public_point(signal_id, float(lat), float(lon))
        condition = str(payload.get("vessel_condition") or "reported distress").replace("_", " ")
        channel = str(payload.get("source_channel") or row["source_channel"] or "partner")
        partner_report = channel in {"webhook", "api", "partner"}
        features.append(
            {
                "type": "Feature",
                "id": f"signal:{signal_id}",
                "geometry": {"type": "Point", "coordinates": [public_lon, public_lat]},
                "properties": {
                    "schema": "org.seacommons.live-signal/v1",
                    "id": f"signal:{signal_id}",
                    "type": "distress",
                    "kind": "distress",
                    "severity": "high" if payload.get("medical_emergency") else "medium",
                    "tier": "operational",
                    "priority": 1,
                    "verification_status": "partner_reported" if partner_report else "user_reported",
                    "publication_status": "published",
                    "title": f"Maritime signal · {condition}"[:255],
                    "text": "",
                    "url": "",
                    "source": "partner intake" if partner_report else "community report",
                    "channel": channel,
                    "location_precision": "approximate",
                    "location_uncertainty_m": 2500,
                    "timestamp_utc": payload.get("event_time_utc")
                    or payload.get("timestamp_utc")
                    or row["received_at"].replace(tzinfo=timezone.utc).isoformat(),
                    "received_at": payload.get("timestamp_utc")
                    or row["received_at"].replace(tzinfo=timezone.utc).isoformat(),
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
    memory_events = intel_store.events(limit=min(limit * 2, 600), max_age_days=days)
    durable_alarm_phone = intel_store.persisted_events(
        source="Alarm Phone",
        max_age_days=days,
        limit=min(max(limit * 3, 300), 1500),
    )
    by_id = {event.id: event for event in durable_alarm_phone}
    # In-memory objects contain the most recent metadata observations and must
    # win over the durable snapshot when both are present.
    by_id.update({event.id: event for event in memory_events})
    events = list(by_id.values())
    now = datetime.now(timezone.utc)
    by_source: dict[str, list[IntelEvent]] = {}
    for event in events:
        by_source.setdefault(event.source, []).append(event)
    features = []
    for event in events:
        feature = _public_intel_feature(event)
        if not feature or feature["properties"].get("kind") != "distress":
            continue
        if not lifecycle.is_within_live_window(event, now=now):
            # Hard cutoff: a distress marker's total life on Live is bounded,
            # regardless of whether it was ever resolved. Older history lives
            # in the archive/replay views, not the live pulsing map.
            continue
        state = lifecycle.distress_lifecycle(event, now=now, same_source=by_source.get(event.source, []))
        # kind: "distress" (red, active) | "resolved" (green) | "archived" (gray)
        # — all three pulse on the map; only fill color differs.
        feature["properties"]["kind"] = "distress" if state == "active" else state
        feature["properties"]["incident_lifecycle"] = state
        features.append(feature)
    features.extend(_published_ingested_features(limit))
    if since:
        features = [
            feature
            for feature in features
            if str(feature["properties"].get("timestamp_utc") or "") > since
        ]
    # Live is a timeline: newest source timestamp always wins. Severity remains
    # a visual attribute and filter, never a second sort that can place an old
    # critical item above a newly received report.
    features.sort(
        key=lambda f: str(f["properties"].get("timestamp_utc") or ""),
        reverse=True,
    )
    features = features[:limit]

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "schema": "org.seacommons.live-feed/v1",
            "total": len(features),
            "memory_candidates": len(memory_events),
            "durable_alarm_phone_candidates": len(durable_alarm_phone),
            "with_coords": sum(
                1 for feature in features if feature.get("geometry") is not None
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "privacy": "published signals only; private identifiers and raw messages excluded",
        },
    }


def _public_drift_feature(
    feature: dict[str, Any],
    *,
    event_id: str,
    title: str,
    source: str,
    severity: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    return {
        "type": "Feature",
        "geometry": feature.get("geometry"),
        "properties": {
            "type": properties.get("type"),
            "horizon_h": properties.get("horizon_h"),
            "radius_m": properties.get("radius_m"),
            "timestamps_utc": properties.get("timestamps_utc"),
            "speed_ms": properties.get("speed_ms"),
            "speed_kn": properties.get("speed_kn"),
            "course_deg": properties.get("course_deg"),
            "distance_m": properties.get("distance_m"),
            "mean_speed_ms": properties.get("mean_speed_ms"),
            "max_speed_ms": properties.get("max_speed_ms"),
            "sample_interval_s": properties.get("sample_interval_s"),
            "sample_count": properties.get("sample_count"),
            "elapsed_hours": properties.get("elapsed_hours"),
            "estimate_time_utc": properties.get("estimate_time_utc"),
            "trajectory_state": properties.get("trajectory_state"),
            "intel_event_id": event_id,
            "intel_title": title[:80],
            "intel_source": source[:64],
            "intel_severity": severity,
            "auto_drift": True,
            "publication_status": "published",
            "trajectory_kind": "model_forecast",
            "observed_track": False,
            "model": metadata.get("model"),
            "forcing_resolution": metadata.get("forcing_resolution"),
            "forcing_quality": metadata.get("forcing_quality"),
            "verification_status": "modelled_spatiotemporal",
        },
    }


def _current_trajectory_estimate(
    trajectory: dict[str, Any],
    *,
    event_timestamp: str,
    now: Optional[datetime] = None,
) -> Optional[dict[str, Any]]:
    """Interpolate the modelled position at wall-clock time."""
    geometry = trajectory.get("geometry") or {}
    properties = trajectory.get("properties") or {}
    coordinates = geometry.get("coordinates") or []
    timestamps = properties.get("timestamps_utc") or []
    if len(coordinates) < 2 or len(timestamps) != len(coordinates):
        return None
    try:
        parsed_times = [
            datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
            for value in timestamps
        ]
        event_time = datetime.fromisoformat(event_timestamp.replace("Z", "+00:00"))
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        event_time = event_time.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if current <= parsed_times[0]:
        coordinate = coordinates[0]
        state = "before_model_start"
    elif current >= parsed_times[-1]:
        coordinate = coordinates[-1]
        state = "model_horizon_reached"
    else:
        upper = next(index for index, value in enumerate(parsed_times) if value >= current)
        lower = upper - 1
        span = max(1.0, (parsed_times[upper] - parsed_times[lower]).total_seconds())
        ratio = (current - parsed_times[lower]).total_seconds() / span
        coordinate = [
            float(coordinates[lower][0])
            + (float(coordinates[upper][0]) - float(coordinates[lower][0])) * ratio,
            float(coordinates[lower][1])
            + (float(coordinates[upper][1]) - float(coordinates[lower][1])) * ratio,
        ]
        state = "interpolated"
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": coordinate[:2]},
        "properties": {
            "type": "current_estimate",
            "elapsed_hours": round(max(0.0, (current - event_time).total_seconds() / 3600), 2),
            "estimate_time_utc": current.isoformat(),
            "trajectory_state": state,
        },
    }


def _is_publishable_live_drift(drift: dict[str, Any]) -> bool:
    """Only expose model runs backed by varying forcing, never demo fallbacks."""
    metadata = drift.get("metadata") or {}
    trajectory = drift.get("trajectory") or {}
    properties = trajectory.get("properties") or {}
    coordinates = (trajectory.get("geometry") or {}).get("coordinates") or []
    return bool(
        drift.get("status") == "completed"
        and metadata.get("model") == "OpenDrift Leeway"
        and metadata.get("forcing_quality") == "spatiotemporal"
        and metadata.get("operational_use") is True
        and len(coordinates) >= 2
        and len(properties.get("timestamps_utc") or []) == len(coordinates)
        and len(properties.get("speed_ms") or []) == len(coordinates)
    )


def public_drift_collection(limit: int = 100) -> dict[str, Any]:
    """Published model geometry linked to received public signals, without raw content."""
    from core.db.store import get_drift, list_drift_jobs_for_event

    features: list[dict[str, Any]] = []
    drift_count = 0
    drift_events = {
        event.id: event
        for event in intel_store.persisted_events(
            source="Alarm Phone", max_age_days=30, limit=min(limit * 5, 1000)
        )
    }
    drift_events.update({
        event.id: event for event in intel_store.events(limit=min(limit * 3, 500))
    })
    now = datetime.now(timezone.utc)
    by_source: dict[str, list[IntelEvent]] = {}
    for event in drift_events.values():
        by_source.setdefault(event.source, []).append(event)
    for event in drift_events.values():
        public_event = _public_intel_feature(event)
        job_id = event.metadata.get("drift_job_id")
        if public_event is None:
            continue
        # Once an incident is resolved or archived, the search is over --
        # an active-looking pulsing drift cone still on the map reads as
        # "still adrift, still searching", which is exactly wrong for a
        # case that's already been rescued or gone stale.
        state = lifecycle.distress_lifecycle(
            event, now=now, same_source=by_source.get(event.source, []),
        )
        if state != "active":
            continue
        if not job_id:
            jobs = list_drift_jobs_for_event(f"intel:{event.id}")
            completed = [job for job in jobs if job.get("status") == "completed"]
            job_id = completed[0].get("id") if completed else None
        if not job_id:
            continue
        drift = get_drift(job_id)
        if not drift or not _is_publishable_live_drift(drift):
            continue
        metadata = drift.get("metadata") or {}
        drift_count += 1
        for feature in (drift.get("trajectory"), drift.get("cone_24h")):
            if feature:
                features.append(
                    _public_drift_feature(
                        feature,
                        event_id=event.id,
                        title=event.title,
                        source=event.source,
                        severity=event.severity,
                        metadata=metadata,
                    )
                )
        current_estimate = _current_trajectory_estimate(
            drift.get("trajectory") or {},
            event_timestamp=event.timestamp_utc,
        )
        if current_estimate:
            features.append(
                _public_drift_feature(
                    current_estimate,
                    event_id=event.id,
                    title=event.title,
                    source=event.source,
                    severity=event.severity,
                    metadata=metadata,
                )
            )
        for feature in (drift.get("impact_point") or {}).get("features", []):
            features.append(
                _public_drift_feature(
                    feature,
                    event_id=event.id,
                    title=event.title,
                    source=event.source,
                    severity=event.severity,
                    metadata=metadata,
                )
            )
        if drift_count >= limit:
            break
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "schema": "org.seacommons.live-drift/v1",
            "drifts": drift_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "privacy": "derived geometry and published signal metadata only",
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
async def live_archives(limit: int = Query(8, ge=1, le=20)):
    """Anonymised recent simulation index for Play."""
    from core.db.store import list_alerts

    archives = []
    for alert in list_alerts(limit=limit * 3):
        event = alert.get("event") or {}
        if alert.get("status") != "completed":
            continue
        archives.append(
            {
                "id": alert["event_id"],
                "timestamp": event.get("timestamp"),
                "lat": event.get("lat"),
                "lon": event.get("lon"),
                "vessel_type": event.get("vessel_type") or "case",
                "persons": event.get("persons") or 1,
            }
        )
        if len(archives) >= limit:
            break
    return {"archives": archives, "generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/archives/{event_id}/geojson")
async def live_archive_geojson(event_id: str):
    """Derived geometry for a public Play archive; no source message or identity."""
    from fastapi import HTTPException
    from core.db.store import get_alert, get_drift

    alert = get_alert(event_id)
    drift = get_drift(event_id)
    if alert is None or alert.get("status") != "completed" or not drift or drift.get("status") != "completed":
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
            "Alarm Phone / X official site",
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
        ("Alarm Phone / X official site", "twitter", True),
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
                "status": observed["status"] if observed else ("active" if configured else "offline"),
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
                source["name"] == "Alarm Phone / X official site"
                and source["status"] == "active"
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
