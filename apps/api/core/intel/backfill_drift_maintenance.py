# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auditable Drift-row maintenance command (docs/fixes.md M8).

One item off M8's specific legacy-cleanup list: "clean stuck/invalid Drift
rows through an auditable maintenance command." Same restartable/
idempotent/dry-run-first pattern as core.intel.backfill_alarm_phone
(this codebase's existing precedent) -- ``find_candidates()`` +
``run(*, apply, limit)`` returning a report dict, ``apply=False`` (the
default posture in every call site) never writes anything.

Two maintenance categories:

  stuck      -- status="computing" and older than STUCK_AFTER_S. A drift
                worker that crashed or was killed mid-run leaves its job
                permanently "computing"; nothing ever marks it failed on
                its own. STUCK_AFTER_S (2 hours) is generous relative to
                a real run, which core.intel.drift_service sizes to
                24-72h *simulation* duration, not wall-clock compute time
                -- actual compute is minutes, not hours.
  invalid    -- status="completed" but missing required geometry
                (trajectory/cone_6h/cone_12h/cone_24h). A row that
                somehow reached "completed" without real output is not
                safe to serve to a caller expecting a usable trajectory.

"Retain immutable original values/provenance so backfill never destroys
source history" (M8): a maintenance pass never deletes a row. It marks
status="failed" and appends a maintenance note to metadata_json,
preserving whatever partial data (lat/lon, event_id, any geometry that
IS present) the row already carried.

Restartable/idempotent by construction: find_candidates() only ever
matches rows still in a stuck/invalid state, so re-running after a
partial or repeated apply touches nothing already fixed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

STUCK_AFTER_S = 2 * 3600
_REPORT_KEYS = ("scanned", "stuck", "invalid", "fixed")


@dataclass(frozen=True)
class DriftMaintenanceCandidate:
    drift_id: str
    event_id: Optional[str]
    status: str
    created_at: datetime
    reason: str  # "stuck" | "invalid"


def _is_missing_geometry(row: Any) -> bool:
    return not (row.trajectory and row.cone_6h and row.cone_12h and row.cone_24h)


def find_candidates(*, limit: int = 500, now: Optional[datetime] = None) -> list[DriftMaintenanceCandidate]:
    """Every drift_results row currently stuck or invalid, oldest first --
    the oldest stuck jobs are the ones most confidently abandoned, not a
    worker still legitimately mid-run."""
    from sqlalchemy import select

    from core.db.models import DriftResultDB
    from core.db.session import session_scope

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=STUCK_AFTER_S)
    # DriftResultDB.created_at is stored naive (this codebase's
    # convention -- see core.intel.source_observation's own note on the
    # same SQLite tz-round-trip behaviour); compare against a naive cutoff.
    cutoff_naive = cutoff.replace(tzinfo=None)

    candidates: list[DriftMaintenanceCandidate] = []
    with session_scope() as db:
        rows = db.execute(
            select(DriftResultDB).order_by(DriftResultDB.created_at.asc()).limit(limit)
        ).scalars().all()
        for row in rows:
            created_at = row.created_at
            if row.status == "computing" and created_at is not None and created_at < cutoff_naive:
                candidates.append(
                    DriftMaintenanceCandidate(
                        drift_id=row.drift_id, event_id=row.event_id,
                        status=row.status, created_at=created_at, reason="stuck",
                    )
                )
            elif row.status == "completed" and _is_missing_geometry(row):
                candidates.append(
                    DriftMaintenanceCandidate(
                        drift_id=row.drift_id, event_id=row.event_id,
                        status=row.status, created_at=created_at, reason="invalid",
                    )
                )
    return candidates


def _mark_failed(drift_id: str, *, reason: str) -> None:
    from core.db.models import DriftResultDB
    from core.db.session import session_scope

    with session_scope() as db:
        row = db.get(DriftResultDB, drift_id)
        if row is None:
            return
        row.status = "failed"
        meta = dict(row.metadata_json or {})
        maintenance_log = list(meta.get("maintenance_log") or [])
        maintenance_log.append(
            {
                "action": "marked_failed",
                "reason": reason,
                "at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            }
        )
        meta["maintenance_log"] = maintenance_log
        row.metadata_json = meta


def run(*, apply: bool = False, limit: int = 500) -> dict[str, int]:
    """``apply=False`` (every call site's default): counts only, writes
    nothing. ``apply=True``: marks each candidate status="failed" with an
    audit note, preserving the row and all its existing data.
    """
    candidates = find_candidates(limit=limit)
    report = {key: 0 for key in _REPORT_KEYS}
    report["scanned"] = len(candidates)

    for candidate in candidates:
        report[candidate.reason] += 1
        if apply:
            _mark_failed(candidate.drift_id, reason=candidate.reason)
            report["fixed"] += 1

    return report
