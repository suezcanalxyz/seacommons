# SPDX-License-Identifier: AGPL-3.0-or-later
"""Coverage-change integrity (docs/updates.md P1.3).

**Goal:** "A high-yield new source can create an artificial trend
break." Before a new source is used for comparative trends, its
inclusion rationale, unique-event yield, and historical-availability
must be recorded -- and coverage-profile changes over time must be
versioned, not silently absorbed into the running numbers.

v0 scope, honestly bounded:
  - ``record_coverage_change`` is an explicit, append-only log write --
    NOT auto-wired into core.intel.source_registry.SourceRegistry.register()
    yet. Every poll cycle calls register() idempotently; firing a
    synchronous DB write from inside its lock on first-registration
    would add I/O to a hot, lock-held path for a benefit (automatic
    detection) that a maintainer's own explicit call already gives
    honestly today. Auto-wiring detection of a brand-new source is a
    separate, deliberately deferred packet.
  - ``compute_unique_event_yield`` is real: every event actually
    persisted to IntelEventDB already passed intel_store's own content-
    hash dedup before being written (core.intel.store.IntelStore.add),
    so a plain per-source row count over the window IS the unique-event
    yield, not an approximation of it.
  - "duplicate/correlation yield" (P1.3's other named yield metric) is
    NOT_YET_COMPUTABLE -- it requires knowing which events across
    *different* sources corroborate the same real-world case, which is
    P2.1's correlation/entity-resolution job, not invented here.
  - "backfill when feasible" / "backfill status" is NOT_YET_COMPUTABLE
    -- no backfill mechanism exists in this codebase yet.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

_EVENT_TYPES = frozenset({"added", "removed", "method_changed", "coverage_break"})

NOT_YET_COMPUTABLE: dict[str, str] = {
    "duplicate_correlation_yield": "needs P2.1 correlation/entity-resolution decisions",
    "backfill_status": "no backfill mechanism exists in this codebase yet",
}


@dataclass(frozen=True)
class CoverageChangeEvent:
    id: str
    source_name: str
    event_type: str
    rationale: Optional[str]
    profile_version: int
    recorded_at: str


def record_coverage_change(
    source_name: str, event_type: str, rationale: Optional[str] = None,
) -> CoverageChangeEvent:
    """Appends one coverage-change event, incrementing that source's
    profile_version. Never edits or collapses a prior entry -- the
    version history itself is the audit trail P1.3 asks for."""
    if event_type not in _EVENT_TYPES:
        raise ValueError(f"event_type must be one of {sorted(_EVENT_TYPES)}, got {event_type!r}")

    from core.db.models import SourceCoverageEventDB
    from core.db.session import session_scope

    now = datetime.now(timezone.utc)
    with session_scope() as db:
        prior_version = (
            db.query(SourceCoverageEventDB)
            .filter(SourceCoverageEventDB.source_name == source_name)
            .order_by(SourceCoverageEventDB.profile_version.desc())
            .first()
        )
        next_version = (prior_version.profile_version if prior_version else 0) + 1
        row = SourceCoverageEventDB(
            id=str(uuid.uuid4()), source_name=source_name, event_type=event_type,
            rationale=rationale, profile_version=next_version,
            recorded_at=now.replace(tzinfo=None),
        )
        db.add(row)
        db.flush()
        return CoverageChangeEvent(
            id=row.id, source_name=row.source_name, event_type=row.event_type,
            rationale=row.rationale, profile_version=row.profile_version,
            recorded_at=now.isoformat(),
        )


def get_coverage_change_log(
    source_name: Optional[str] = None, limit: int = 200,
) -> list[CoverageChangeEvent]:
    from core.db.models import SourceCoverageEventDB
    from core.db.session import session_scope

    with session_scope() as db:
        query = db.query(SourceCoverageEventDB)
        if source_name is not None:
            query = query.filter(SourceCoverageEventDB.source_name == source_name)
        rows = query.order_by(SourceCoverageEventDB.recorded_at.desc()).limit(limit).all()
        return [
            CoverageChangeEvent(
                id=r.id, source_name=r.source_name, event_type=r.event_type,
                rationale=r.rationale, profile_version=r.profile_version,
                recorded_at=r.recorded_at.isoformat(),
            )
            for r in rows
        ]


def compute_unique_event_yield(source_name: str, hours: int = 168) -> int:
    """Real count of IntelEventDB rows for this source in the window --
    every persisted row already survived intel_store's own dedup before
    being written, so this count IS the unique-event yield."""
    from datetime import timedelta

    from core.db.models import IntelEventDB
    from core.db.session import session_scope

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with session_scope() as db:
        return (
            db.query(IntelEventDB)
            .filter(IntelEventDB.source == source_name, IntelEventDB.timestamp_utc >= cutoff)
            .count()
        )


def historical_availability(source_name: str) -> Optional[str]:
    """Earliest IntelEventDB.timestamp_utc on record for this source, or
    None if the source has never produced a persisted event -- the real
    "observed since" this codebase can honestly answer, not a claim
    about the source's actual historical archive depth."""
    from core.db.models import IntelEventDB
    from core.db.session import session_scope

    with session_scope() as db:
        row = (
            db.query(IntelEventDB)
            .filter(IntelEventDB.source == source_name)
            .order_by(IntelEventDB.timestamp_utc.asc())
            .first()
        )
        return row.timestamp_utc if row is not None else None
