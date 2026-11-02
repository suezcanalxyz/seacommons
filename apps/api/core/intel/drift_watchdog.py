# SPDX-License-Identifier: AGPL-3.0-or-later
"""Restart-safe reconciliation of Alarm Phone drift candidates.

Uses durable records, never the bounded in-memory buffer. This is a recovery
safety net, not a replacement for the ingestion-time trigger or a task queue.
At most one heavy model starts per run, subject to shared model semaphore.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from core.intel.macro_drift import explicit_distress_flag, source_is_alarm_phone, spatial_prior_for_event

RETRY_AFTER = timedelta(minutes=30)
STUCK_AFTER = timedelta(hours=2)


def _age(value: Any, now: datetime) -> timedelta | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return now - parsed
    except (ValueError, TypeError):
        return None


def _defer_retry(status: str, since: timedelta | None) -> str | None:
    """Classify a recent request, never treating a missing clock as recent.

    Old persisted records may have drift_status but no drift_requested_at.
    Such records must be rechecked against the shared model slot instead of
    remaining permanently "computing" or "pending" after a restart.
    """
    if since is None:
        return None
    if status == "computing" and since < STUCK_AFTER:
        return "precise_running"
    if status in {"failed", "computing"} and since < RETRY_AFTER:
        return "precise_pending"
    return None


def reconcile(*, launch: bool = False, limit: int = 300) -> dict[str, int]:
    """Classify candidates and, optionally, enqueue one missing precise drift.

    launch=False is read-only. Recovery does not overwrite completed products,
    and it won't spin repeatedly on a busy engine or failed request.
    """
    from core.intel.store import ALARM_PHONE_SOURCE_ALIASES, intel_store
    from core.intel.drift_service import (
        drift_origin_coordinates, is_auto_drift_eligible, schedule_intel_drift,
    )
    from core.intel.drift_ownership import get_current_drift_id
    from core.db.store import get_drift
    from core.intel import lifecycle

    now = datetime.now(timezone.utc)
    report = {k: 0 for k in (
        "candidates", "precise_eligible", "precise_completed", "precise_pending",
        "precise_running", "area_prior", "geography_unknown", "terminal",
        "not_eligible", "launched", "busy_or_failed_to_queue",
    )}
    # The watchdog must scan the same durable source aliases as LIVE and drift
    # publication; otherwise a valid @AlarmPhone distress is never scheduled.
    rows = intel_store.persisted_events(
        source_in=list(ALARM_PHONE_SOURCE_ALIASES), max_age_days=2, limit=limit
    )
    for event in rows:
        if not source_is_alarm_phone(event) or not explicit_distress_flag((event.metadata or {}).get("is_distress")):
            continue
        report["candidates"] += 1
        state = str(event.metadata.get("incident_lifecycle") or "").lower()
        if state in {"resolved", "archived"} or not lifecycle.is_within_live_window(event, now=now):
            report["terminal"] += 1
            continue
        eligible, _ = is_auto_drift_eligible(event)
        if not eligible:
            prior = spatial_prior_for_event(event)
            report["area_prior" if prior["geometry"] else "geography_unknown"] += 1
            continue
        report["precise_eligible"] += 1
        job_id = get_current_drift_id(event.id)
        if job_id:
            result = get_drift(job_id)
            if result and result.get("status") == "completed" and result.get("trajectory") and result.get("cone_24h"):
                report["precise_completed"] += 1
                continue
        meta = event.metadata
        since = _age(meta.get("drift_requested_at"), now)
        status = str(meta.get("drift_status") or "")
        deferred = _defer_retry(status, since)
        if deferred:
            report[deferred] += 1
            continue
        report["precise_pending"] += 1
        if launch and report["launched"] == 0:
            origin_lat, origin_lon = drift_origin_coordinates(event)
            accepted = schedule_intel_drift(
                event.id, float(origin_lat), float(origin_lon),
                (int(meta["persons"]) if str(meta.get("persons", "")).isdigit() else None),
                str(meta.get("vessel_type") or "rubber_boat"),
                event.timestamp_utc,
                force=True,  # confirmed missing owner; old status may be stale
            )
            if accepted:
                report["launched"] += 1
            else:
                report["busy_or_failed_to_queue"] += 1
    return report
