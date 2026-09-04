# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backfill HumanitarianIncident.current_drift_id (docs/updates.md P0.11).

Same auditable, dry-run-first maintenance-command pattern as
core.intel.backfill_drift_maintenance / core.intel.backfill_alarm_phone:
``find_candidates()`` + ``run(*, apply, limit)`` returning a report
dict, ``apply=False`` (every call site's default) never writes.

**Why a maintenance command, not an auto-run migration:** core.intel.
drift_service now sets current_drift_id going forward, the moment a
drift completes (P0.11's own wiring). But any incident whose drift
completed BEFORE this packet never got the pointer set, and would
silently disappear from the public Drift feed the instant
core.live.feed.public_signal_collection cuts over to reading only
current_drift_id -- a real regression for whatever cases happen to be
open at deploy time. Backfilling this from a completed drift job's own
already-recorded event_id is a real, mechanical fix, but "match the
right job for an incident from historical metadata" is exactly the
kind of judgement call this codebase's own established backfill
precedent keeps operator-gated (dry-run first, one command, auditable)
rather than baked into an unconditional auto-run migration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_REPORT_KEYS = ("scanned", "backfilled", "skipped_terminal")


@dataclass(frozen=True)
class CurrentDriftBackfillCandidate:
    incident_id: str
    drift_job_id: str


def find_candidates(*, limit: int = 500) -> list[CurrentDriftBackfillCandidate]:
    """Every open (active/needs_review) HumanitarianIncident with no
    current_drift_id yet, whose founding event's own metadata already
    names a COMPLETED drift job -- the same event_id-keyed metadata
    core.intel.drift_service has always written (docs/fixes.md M3),
    just never synced onto the incident until P0.11."""
    from core.db.models import HumanitarianIncidentDB, IntelEventDB
    from core.db.session import session_scope

    candidates: list[CurrentDriftBackfillCandidate] = []
    with session_scope() as db:
        rows = (
            db.query(HumanitarianIncidentDB)
            .filter(
                HumanitarianIncidentDB.current_drift_id.is_(None),
                HumanitarianIncidentDB.incident_status.in_(("active", "needs_review")),
            )
            .limit(limit)
            .all()
        )
        for row in rows:
            event = db.get(IntelEventDB, row.incident_id)
            if event is None:
                continue
            meta = event.meta or {}
            if meta.get("drift_status") != "completed":
                continue
            job_id = meta.get("drift_job_id")
            if not job_id:
                continue
            candidates.append(CurrentDriftBackfillCandidate(
                incident_id=row.incident_id, drift_job_id=str(job_id),
            ))
    return candidates


def run(*, apply: bool = False, limit: int = 500) -> dict[str, int]:
    """``apply=False`` (default): counts only, writes nothing.
    ``apply=True``: calls core.intel.drift_ownership.
    sync_current_drift_for_incident for each candidate -- the same
    single-pointer-overwrite function P0.11's own forward-going wiring
    uses, so a backfilled incident is indistinguishable from one synced
    the normal way."""
    from core.intel.drift_ownership import sync_current_drift_for_incident

    candidates = find_candidates(limit=limit)
    report = {key: 0 for key in _REPORT_KEYS}
    report["scanned"] = len(candidates)

    for candidate in candidates:
        if not apply:
            continue
        result = sync_current_drift_for_incident(candidate.incident_id, candidate.drift_job_id)
        if result is None:
            # Lifecycle moved to resolved/archived between find_candidates()
            # and this call (or the incident vanished) -- sync_current_drift_
            # for_incident's own terminal-lifecycle guard already refused it.
            report["skipped_terminal"] += 1
        else:
            report["backfilled"] += 1

    return report
