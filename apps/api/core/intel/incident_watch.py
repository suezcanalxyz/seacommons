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


@dataclass(frozen=True)
class WatchQuery:
    incident_id: str
    profile: dict[str, Any]
    since: datetime | None
    budget: int


@dataclass(frozen=True)
class WatchResult:
    source_name: str
    source_items_seen: int
    observations_created: int
    observations_replayed: int
    checkpoint: str | None
    error_class: str | None


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
                query_fingerprint=None,
                expires_at=_naive_utc(policy.expires_at) if policy.expires_at else None,
            )
            db.add(row)
            db.flush()
        else:
            lifecycle_changed = row.lifecycle_snapshot != snapshot
            row.status = policy.status
            row.priority = policy.priority
            row.lifecycle_snapshot = snapshot
            profile_changed = dict(row.profile_json or {}) != profile
            row.profile_json = profile
            row.profile_version = PROFILE_VERSION
            if profile_changed:
                row.query_fingerprint = None
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

_PRIORITY_ORDER = {"highest": 0, "high": 1, "medium": 2, "low": 3}
MAX_ADAPTERS_PER_RUN = 3
MAX_ACCEPTED_OBSERVATIONS = 25
DEGRADED_RETRY = timedelta(hours=4)


def _run_fingerprint(profile: dict[str, Any], adapter_names: list[str]) -> str:
    payload = {
        "profile": profile,
        "adapters": sorted(adapter_names),
        "profile_version": PROFILE_VERSION,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def claim_due_watches(
    *, now: datetime, limit: int, lease_owner: str, lease_seconds: int = 120,
) -> list[dict[str, Any]]:
    """Atomically claim due watches with an optimistic, restart-safe lease."""
    from sqlalchemy import case, or_

    from core.db.models import IncidentWatchDB
    from core.db.session import session_scope

    if limit <= 0:
        return []
    now_naive = _naive_utc(_aware_utc(now) or datetime.now(timezone.utc))
    lease_until = now_naive + timedelta(seconds=max(1, lease_seconds))
    priority_case = case(
        (IncidentWatchDB.priority == "highest", 0),
        (IncidentWatchDB.priority == "high", 1),
        (IncidentWatchDB.priority == "medium", 2),
        (IncidentWatchDB.priority == "low", 3),
        else_=4,
    )
    claimed: list[dict[str, Any]] = []
    with session_scope() as db:
        candidate_ids = [
            row[0]
            for row in (
                db.query(IncidentWatchDB.watch_id)
                .filter(
                    IncidentWatchDB.status.in_(["active", "degraded"]),
                    IncidentWatchDB.next_run_at <= now_naive,
                    or_(IncidentWatchDB.lease_until.is_(None), IncidentWatchDB.lease_until <= now_naive),
                )
                .order_by(priority_case.asc(), IncidentWatchDB.next_run_at.asc(), IncidentWatchDB.watch_id.asc())
                .limit(limit)
                .all()
            )
        ]
        for watch_id in candidate_ids:
            updated = (
                db.query(IncidentWatchDB)
                .filter(
                    IncidentWatchDB.watch_id == watch_id,
                    IncidentWatchDB.status.in_(["active", "degraded"]),
                    IncidentWatchDB.next_run_at <= now_naive,
                    or_(IncidentWatchDB.lease_until.is_(None), IncidentWatchDB.lease_until <= now_naive),
                )
                .update(
                    {
                        IncidentWatchDB.lease_owner: lease_owner,
                        IncidentWatchDB.lease_until: lease_until,
                    },
                    synchronize_session=False,
                )
            )
            if updated != 1:
                continue
            db.flush()
            row = db.get(IncidentWatchDB, watch_id)
            if row is not None:
                claimed.append(_watch_to_dict(row))
    return claimed


def _eligible_adapters(profile: dict[str, Any], adapters: list[Any]) -> list[Any]:
    eligible: list[Any] = []
    for adapter in adapters:
        try:
            if adapter.eligible(profile):
                eligible.append(adapter)
        except Exception:
            continue
        if len(eligible) >= MAX_ADAPTERS_PER_RUN:
            break
    return eligible


def run_claimed_watch(
    watch_id: str, *, adapters: list[Any] | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    """Execute one bounded watch without ever writing canonical incident truth."""
    from core.db.models import HumanitarianIncidentDB, IncidentWatchDB
    from core.db.session import session_scope

    now_aware = _aware_utc(now) or datetime.now(timezone.utc)
    now_naive = _naive_utc(now_aware)
    adapter_list = list(_default_adapters() if adapters is None else adapters)

    with session_scope() as db:
        row = db.query(IncidentWatchDB).filter_by(incident_id=watch_id).one_or_none()
        if row is None:
            row = db.get(IncidentWatchDB, watch_id)
        if row is None:
            return {"executed": False, "reason": "watch_not_found"}
        incident = db.get(HumanitarianIncidentDB, row.incident_id)
        if incident is None:
            row.status = "expired"
            row.lease_owner = None
            row.lease_until = None
            return {"executed": False, "reason": "incident_not_found"}
        policy = policy_for_state(
            incident_status=incident.incident_status,
            lifecycle=incident.lifecycle,
            resolved_at=incident.resolved_at,
            now=now_aware,
        )
        if policy.status == "expired" or policy.cadence is None:
            row.status = "expired"
            row.expires_at = _naive_utc(policy.expires_at) if policy.expires_at else now_naive
            row.lease_owner = None
            row.lease_until = None
            return {"executed": False, "reason": "watch_expired"}
        profile = dict(row.profile_json or {})
        eligible = _eligible_adapters(profile, adapter_list)
        fingerprint = _run_fingerprint(profile, [str(a.name) for a in eligible])
        last_run = _aware_utc(row.last_run_at)
        if (
            row.query_fingerprint == fingerprint
            and last_run is not None
            and now_aware - last_run < policy.cadence
        ):
            row.next_run_at = _naive_utc(last_run + policy.cadence)
            row.lease_owner = None
            row.lease_until = None
            return {
                "executed": False,
                "reason": "duplicate_fingerprint_within_cadence",
            }
        incident_id = row.incident_id
        since = _aware_utc(row.last_success_at)

    created = 0
    replayed = 0
    seen = 0
    error: Exception | None = None
    remaining = MAX_ACCEPTED_OBSERVATIONS
    for adapter in eligible:
        if remaining <= 0:
            break
        query = WatchQuery(
            incident_id=incident_id, profile=profile, since=since, budget=remaining,
        )
        try:
            result = adapter.run(query)
            seen += max(0, int(result.source_items_seen))
            created += max(0, int(result.observations_created))
            replayed += max(0, int(result.observations_replayed))
            remaining = max(0, MAX_ACCEPTED_OBSERVATIONS - created)
            if result.error_class:
                error = RuntimeError(result.error_class)
                break
        except Exception as exc:  # local failure: never mutate the incident
            error = exc
            break

    with session_scope() as db:
        row = db.query(IncidentWatchDB).filter_by(incident_id=incident_id).one()
        row.run_count = (row.run_count or 0) + 1
        row.last_run_at = now_naive
        row.query_fingerprint = fingerprint
        row.lease_owner = None
        row.lease_until = None
        if error is None:
            row.last_success_at = now_naive
            row.last_error_at = None
            row.last_error_class = None
            row.consecutive_errors = 0
            row.status = policy.status
            row.priority = policy.priority
            row.next_run_at = _naive_utc(now_aware + policy.cadence)
        else:
            row.last_error_at = now_naive
            row.last_error_class = error.__class__.__name__
            row.consecutive_errors = (row.consecutive_errors or 0) + 1
            if row.consecutive_errors >= 3:
                row.status = "degraded"
                retry = max(policy.cadence, DEGRADED_RETRY)
            else:
                retry = policy.cadence
            row.next_run_at = _naive_utc(now_aware + retry)

    return {
        "executed": True,
        "success": error is None,
        "source_items_seen": seen,
        "observations_created": created,
        "observations_replayed": replayed,
        "error_class": error.__class__.__name__ if error is not None else None,
    }

class _OfficialXWatchAdapter:
    name = "X / Twitter"

    def __init__(self, monitor) -> None:
        self._monitor = monitor

    def eligible(self, profile: dict[str, Any]) -> bool:
        return bool(self._monitor.configured and profile.get("source_item_ids"))

    def run(self, query: WatchQuery) -> WatchResult:
        remaining = max(0, min(int(query.budget), MAX_ACCEPTED_OBSERVATIONS))
        seen = created = replayed = 0
        checkpoint = None
        watch_id = watch_id_for_incident(query.incident_id)
        for source_item_id in list(query.profile.get("source_item_ids") or []):
            if remaining <= 0:
                break
            result = self._monitor.watch_conversation(
                str(source_item_id),
                watch_id=watch_id,
                incident_id=query.incident_id,
                budget=remaining,
            )
            seen += result.source_items_seen
            created += result.observations_created
            replayed += result.observations_replayed
            checkpoint = result.checkpoint or checkpoint
            remaining = max(0, remaining - result.observations_created)
        return WatchResult(
            source_name=self.name,
            source_items_seen=seen,
            observations_created=created,
            observations_replayed=replayed,
            checkpoint=checkpoint,
            error_class=None,
        )


def _default_adapters() -> list[Any]:
    """Return only already-running, explicitly watch-capable adapters."""
    try:
        from core.intel.engine import intel_engine

        monitor = intel_engine._twitter
        if monitor is not None and getattr(monitor, "configured", False):
            return [_OfficialXWatchAdapter(monitor)]
    except Exception:
        pass
    return []

