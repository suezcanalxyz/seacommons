# SPDX-License-Identifier: AGPL-3.0-or-later
"""Privacy-preserving Live projections and feed composition."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from core.domain.live_contracts import (
    LIVE_SIGNAL_SCHEMA,
    IncidentLifecycle,
    IntelTier,
    LiveSignalKind,
    LocationPrecision,
    PublicationStatus,
    SourcePolicy,
    VerificationStatus,
    validate_live_signal,
)
from core.intel import lifecycle
from core.intel.store import IntelEvent, intel_store
from core.live.projection import (
    _approximate_public_point,
    _current_trajectory_estimate,
    _is_publishable_live_drift,
    _public_drift_feature,
    _public_intel_feature,
)

logger = logging.getLogger(__name__)


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
    except Exception:  # noqa: BLE001 - public feed fails closed when storage is unavailable
        return []

    features: list[dict[str, Any]] = []
    for row in rows:
        payload = row["payload"]
        if payload.get("publication_status") != PublicationStatus.PUBLISHED.value:
            continue
        lat, lon = payload.get("lat"), payload.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        signal_id = str(payload.get("signal_id") or row["signal_id"])
        public_lat, public_lon = _approximate_public_point(signal_id, float(lat), float(lon))
        condition = str(payload.get("vessel_condition") or "reported distress").replace("_", " ")
        channel = str(payload.get("source_channel") or row["source_channel"] or "partner")
        partner_report = channel in {"webhook", "api", "partner"}
        feature = {
            "type": "Feature",
            "id": f"signal:{signal_id}",
            "geometry": {"type": "Point", "coordinates": [public_lon, public_lat]},
            "properties": {
                "schema": LIVE_SIGNAL_SCHEMA,
                "id": f"signal:{signal_id}",
                "type": "distress",
                "kind": LiveSignalKind.DISTRESS.value,
                "severity": "high" if payload.get("medical_emergency") else "medium",
                "tier": IntelTier.OPERATIONAL.value,
                "priority": 1,
                "verification_status": VerificationStatus.PARTNER_REPORTED.value
                if partner_report
                else VerificationStatus.USER_REPORTED.value,
                "publication_status": PublicationStatus.PUBLISHED.value,
                "source_policy": SourcePolicy.OPERATOR_PUBLISHED.value,
                "title": f"Maritime signal · {condition}"[:255],
                "text": "",
                "url": "",
                "source": "partner intake" if partner_report else "community report",
                "channel": channel,
                "location_precision": LocationPrecision.APPROXIMATE.value,
                "location_uncertainty_m": 2500,
                "incident_lifecycle": IncidentLifecycle.ACTIVE.value,
                "timestamp_utc": payload.get("event_time_utc")
                or payload.get("timestamp_utc")
                or row["received_at"].replace(tzinfo=UTC).isoformat(),
                "received_at": payload.get("timestamp_utc")
                or row["received_at"].replace(tzinfo=UTC).isoformat(),
            },
        }
        try:
            features.append(validate_live_signal(feature))
        except ValueError:
            logger.warning("Dropping ingested signal that violates Live contract id=%s", signal_id)
            continue
        if len(features) >= limit:
            break
    return features


def public_signal_collection(
    *,
    limit: int = 300,
    days: int = 30,
    since: str | None = None,
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
    now = datetime.now(UTC)
    by_source: dict[str, list[IntelEvent]] = {}
    for event in events:
        by_source.setdefault(event.source, []).append(event)
    features = []
    context_features: list[dict[str, Any]] = []
    for event in events:
        feature = _public_intel_feature(event)
        if not feature:
            continue
        kind = feature["properties"].get("kind")
        if kind == "distress" and event.type != "correlated_alert":
            if not lifecycle.is_within_live_window(event, now=now):
                # Hard cutoff: a distress marker's total life on Live is bounded,
                # regardless of whether it was ever resolved. Older history lives
                # in the archive/replay views, not the live pulsing map.
                continue
            state = lifecycle.distress_lifecycle(
                event, now=now, same_source=by_source.get(event.source, [])
            )
            # Directly resolved incidents were filtered above. Cross-post matches
            # may still project resolved; ambiguous replies project needs_review.
            feature["properties"]["kind"] = LiveSignalKind.DISTRESS.value
            feature["properties"]["incident_lifecycle"] = state
            features.append(feature)
        elif kind in ("context", "distress"):
            # Broader OSINT context: news, AIS anomalies, GDACS, vessel
            # incidents, correlated fusion alerts — eligibility (type + maritime
            # compartment) is already decided in _public_intel_feature. Bounded
            # by the same age window, no pulsing lifecycle. Kept in a separate
            # bucket and capped so a chatty context source can never crowd a
            # genuine distress report out of the window.
            if not lifecycle.is_within_live_window(event, now=now):
                continue
            context_features.append(feature)
    context_features.sort(
        key=lambda f: str(f["properties"].get("timestamp_utc") or ""), reverse=True
    )
    context_cap = max(0, min(limit - len(features), max(30, limit // 2)))
    features.extend(context_features[:context_cap])
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
            "with_coords": sum(1 for feature in features if feature.get("geometry") is not None),
            "generated_at": datetime.now(UTC).isoformat(),
            "privacy": "published signals only; private identifiers and raw messages excluded",
        },
    }


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
    drift_events.update(
        {event.id: event for event in intel_store.events(limit=min(limit * 3, 500))}
    )
    now = datetime.now(UTC)
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
            event,
            now=now,
            same_source=by_source.get(event.source, []),
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
            "generated_at": datetime.now(UTC).isoformat(),
            "privacy": "derived geometry and published signal metadata only",
        },
    }
