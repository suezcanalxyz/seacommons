# SPDX-License-Identifier: AGPL-3.0-or-later
"""Restart-safe bounded follow-up for canonical Humanitarian incidents."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

PROFILE_VERSION = 1
PROFILE_METHOD_VERSION = "v0_explicit_persisted_fields"


@dataclass(frozen=True)
class WatchPolicy:
    status: str
    priority: str
    cadence: timedelta | None
    expires_at: datetime | None = None


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def policy_for_state(
    *, incident_status: str, lifecycle: str, resolved_at: datetime | None,
    now: datetime,
) -> WatchPolicy:
    """Return deterministic follow-up cadence from canonical incident state."""
    now_aware = _aware_utc(now) or datetime.now(timezone.utc)
    status = str(incident_status or "").lower()
    lifecycle = str(lifecycle or "").lower()

    if status == "outcome_unknown":
        return WatchPolicy("active", "medium", timedelta(hours=2))
    if status == "needs_review" or lifecycle == "needs_review":
        return WatchPolicy("active", "high", timedelta(minutes=30))
    if status == "active" or lifecycle in {"active", "reported", "reopened"}:
        return WatchPolicy("active", "highest", timedelta(minutes=15))
    if status == "resolved" or lifecycle == "resolved":
        resolved = _aware_utc(resolved_at) or now_aware
        age = max(timedelta(0), now_aware - resolved)
        if age <= timedelta(hours=24):
            return WatchPolicy("active", "high", timedelta(hours=1), resolved + timedelta(days=30))
        if age <= timedelta(days=7):
            return WatchPolicy("active", "medium", timedelta(hours=12), resolved + timedelta(days=30))
        if age <= timedelta(days=30):
            return WatchPolicy("active", "low", timedelta(hours=24), resolved + timedelta(days=30))
        return WatchPolicy("expired", "low", None, resolved + timedelta(days=30))
    return WatchPolicy("expired", "low", None, now_aware)


def watch_id_for_incident(incident_id: str) -> str:
    digest = hashlib.blake2s(incident_id.encode(), digest_size=16).hexdigest()
    return f"watch:{digest}"


def build_watch_profile(db, incident, *, event_hint=None) -> dict[str, Any]:
    """Build a sparse deterministic profile from explicit persisted evidence only."""
    from core.db.models import IntelEventDB

    event = db.get(IntelEventDB, incident.incident_id)
    if event is None and event_hint is not None:
        event = event_hint
    raw_meta = getattr(event, "meta", None) if event is not None else None
    if raw_meta is None and event is not None:
        raw_meta = getattr(event, "metadata", None)
    meta = dict(raw_meta or {})
    source_item_ids: list[str] = []
    for key in ("tweet_id", "source_id", "provider_message_id"):
        value = meta.get(key)
        if value is not None and str(value) and str(value) not in source_item_ids:
            source_item_ids.append(str(value))

    coordinates: list[dict[str, float]] = []
    if event is not None and getattr(event, "lat", None) is not None and getattr(event, "lon", None) is not None:
        coordinate: dict[str, float] = {"lat": float(event.lat), "lon": float(event.lon)}
        uncertainty = getattr(event, "location_uncertainty_m", None)
        if uncertainty is None:
            uncertainty = meta.get("location_uncertainty_m")
        if uncertainty is not None:
            coordinate["uncertainty_m"] = float(uncertainty)
        coordinates.append(coordinate)

    return {
        "schema_version": PROFILE_VERSION,
        "incident_id": incident.incident_id,
        "source_thread_ids": [],
        "source_item_ids": source_item_ids,
        "source_names": [event.source] if event is not None and getattr(event, "source", "") else [],
        "coordinates": coordinates,
        "uncertainty_m": (
            float(getattr(event, "location_uncertainty_m", None) or meta.get("location_uncertainty_m"))
            if event is not None and (getattr(event, "location_uncertainty_m", None) is not None or meta.get("location_uncertainty_m") is not None)
            else None
        ),
        "named_places": [],
        "route_terms": [],
        "departure_terms": [],
        "destination_terms": [],
        "people_min": None,
        "people_max": None,
        "vessel_description_terms": [],
        "actor_names": [],
        "keywords": [],
        "language_hints": [],
        "source_observation_ids": list(incident.source_observation_ids or []),
        "profile_method_version": PROFILE_METHOD_VERSION,
    }


def _profile_fingerprint(profile: dict[str, Any]) -> str:
    payload = json.dumps(profile, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _watch_to_dict(row) -> dict[str, Any]:
    return {
        "watch_id": row.watch_id,
        "incident_id": row.incident_id,
        "status": row.status,
        "priority": row.priority,
        "lifecycle_snapshot": row.lifecycle_snapshot,
        "profile_json": dict(row.profile_json or {}),
        "profile_version": row.profile_version,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
        "last_error_at": row.last_error_at.isoformat() if row.last_error_at else None,
        "last_error_class": row.last_error_class,
        "consecutive_errors": row.consecutive_errors,
        "run_count": row.run_count,
        "query_fingerprint": row.query_fingerprint,
        "lease_owner": row.lease_owner,
        "lease_until": row.lease_until.isoformat() if row.lease_until else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


def sync_watch_for_incident(incident_id: str, *, now: datetime | None = None, event_hint=None) -> dict[str, Any] | None:
    from core.db.models import HumanitarianIncidentDB, IncidentWatchDB
    from core.db.session import session_scope

    now_aware = _aware_utc(now) or datetime.now(timezone.utc)
    now_naive = _naive_utc(now_aware)
    with session_scope() as db:
        incident = db.get(HumanitarianIncidentDB, incident_id)
        if incident is None:
            return None
        profile = build_watch_profile(db, incident, event_hint=event_hint)
        policy = policy_for_state(
            incident_status=incident.incident_status,
            lifecycle=incident.lifecycle,
            resolved_at=incident.resolved_at,
            now=now_aware,
        )
        snapshot = f"{incident.incident_status}/{incident.lifecycle}"
        row = db.query(IncidentWatchDB).filter_by(incident_id=incident_id).one_or_none()
        if row is None:
            row = IncidentWatchDB(
                watch_id=watch_id_for_incident(incident_id), incident_id=incident_id,
                status=policy.status, priority=policy.priority,
                lifecycle_snapshot=snapshot, profile_json=profile,
                profile_version=PROFILE_VERSION, next_run_at=now_naive,
                consecutive_errors=0, run_count=0,
                query_fingerprint=_profile_fingerprint(profile),
                expires_at=_naive_utc(policy.expires_at) if policy.expires_at else None,
            )
            db.add(row)
            db.flush()
        else:
            lifecycle_changed = row.lifecycle_snapshot != snapshot
            row.status = policy.status
            row.priority = policy.priority
            row.lifecycle_snapshot = snapshot
            row.profile_json = profile
            row.profile_version = PROFILE_VERSION
            row.query_fingerprint = _profile_fingerprint(profile)
            row.expires_at = _naive_utc(policy.expires_at) if policy.expires_at else None
            if lifecycle_changed and policy.cadence is not None:
                row.next_run_at = now_naive
        return _watch_to_dict(row)


def get_watch(incident_id: str) -> dict[str, Any] | None:
    from core.db.models import IncidentWatchDB
    from core.db.session import session_scope

    with session_scope() as db:
        row = db.query(IncidentWatchDB).filter_by(incident_id=incident_id).one_or_none()
        return _watch_to_dict(row) if row is not None else None
