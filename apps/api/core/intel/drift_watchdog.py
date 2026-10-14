# SPDX-License-Identifier: AGPL-3.0-or-later
"""Restart-safe reconciliation of Alarm Phone drift candidates.

Uses durable records, never the bounded in-memory buffer. This is a recovery
safety net, not a replacement for the ingestion-time trigger or a task queue.
At most one heavy model starts per run, subject to shared model semaphore.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from core.intel.macro_drift import source_is_alarm_phone, spatial_prior_for_event

SOURCE_VARIANTS = ["alarm_phone", "Alarm Phone", "alarmphone", "@alarm_phone"]
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


def reconcile(*, launch: bool = False, limit: int = 300) -> dict[str, int]:
    """Classify candidates and, optionally, enqueue one missing precise drift.

    launch=False is read-only. Recovery does not overwrite completed products,
    and it won't spin repeatedly on a busy engine or failed request.
    """
    from core.intel.store import intel_store
    from core.intel.drift_service import is_auto_drift_eligible, schedule_intel_drift
    from core.intel.drift_ownership import get_current_drift_id
    from core.db.store import get_drift
    from core.intel import lifecycle

    now = datetime.now(timezone.utc)
    report = {k: 0 for k in (
        "candidates", "precise_eligible", "precise_completed", "precise_pending",
        "precise_running", "area_prior", "geography_unknown", "terminal",
        "not_eligible", "launched", "busy_or_failed_to_queue",
    )}
    rows = intel_store.persisted_events(source_in=SOURCE_VARIANTS, max_age_days=2, limit=limit)
    for event in rows:
        if not source_is_alarm_phone(event) or not event.metadata.get("is_distress"):
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
        if status == "computing" and (since is None or since < STUCK_AFTER):
            report["precise_running"] += 1
            continue
        if status in {"failed", "computing"} and (since is None or since < RETRY_AFTER):
            report["precise_pending"] += 1
            continue
        report["precise_pending"] += 1
        if launch and report["launched"] == 0:
            accepted = schedule_intel_drift(
                event.id, float(event.lat), float(event.lon),
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
