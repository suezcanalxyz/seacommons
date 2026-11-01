# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded, opt-in AIS context reads for staging maritime incident review.

No collector, scheduler, database mutation, AIS-derived attack classification
or PLAY publication. A caller-supplied PostgreSQL session must already be in
a READ ONLY transaction. Incomplete or inconsistent track batches fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import islice
from typing import Callable, Iterable

from core.intel.maritime_attack_correlation import (
    AISFix, _utc, _valid_mmsi, ais_fix_from_vessel_track,
)


@dataclass(frozen=True)
class AISContextResult:
    fixes: tuple[AISFix, ...] = ()
    track_ids: tuple[int, ...] = ()
    complete: bool = False
    reason: str = ""
    inspected_rows: int = 0


def load_ais_context(
    mmsi: str,
    occurred_at: datetime,
    fetch_rows: Callable[[str, datetime, datetime, int], Iterable[object]],
    *,
    before_minutes: int = 30,
    after_minutes: int = 90,
    max_rows: int = 256,
) -> AISContextResult:
    """Read every track in a bounded event window, not just convenient fixes.

    fetch_rows receives MMSI, aware UTC start/end, and a LIMIT of max_rows+1.
    Any truncation, duplicate row identity, wrong vessel or malformed row
    withholds *all* AIS context; it never suppresses documentary evidence.
    The track IDs allow later inspection of the exact original DB rows.
    """
    if not _valid_mmsi(mmsi):
        raise ValueError("Invalid context MMSI")
    event = _utc(occurred_at)
    if (type(before_minutes) is not int or type(after_minutes) is not int
            or not 0 <= before_minutes <= 180 or not 0 <= after_minutes <= 180
            or before_minutes + after_minutes == 0):
        raise ValueError("Invalid AIS context window")
    if type(max_rows) is not int or not 1 <= max_rows <= 512:
        raise ValueError("Invalid AIS row cap")
    start = event - timedelta(minutes=before_minutes)
    end = event + timedelta(minutes=after_minutes)
    rows = list(islice(fetch_rows(mmsi, start, end, max_rows + 1), max_rows + 1))
    if len(rows) > max_rows:
        return AISContextResult(complete=False, reason="ais_context_row_limit",
                                inspected_rows=len(rows))
    checked: list[tuple[datetime, int, AISFix]] = []
    seen: set[int] = set()
    for row in rows:
        identifier = getattr(row, "id", None)
        if type(identifier) is not int or identifier < 1 or identifier in seen:
            return AISContextResult(complete=False, reason="invalid_or_duplicate_track_id",
                                    inspected_rows=len(rows))
        seen.add(identifier)
        try:
            fix = ais_fix_from_vessel_track(row)
        except (TypeError, ValueError, OverflowError):
            return AISContextResult(complete=False, reason="invalid_vessel_track",
                                    inspected_rows=len(rows))
        if fix.mmsi != mmsi or not start <= fix.observed_at <= end:
            return AISContextResult(complete=False, reason="track_outside_requested_context",
                                    inspected_rows=len(rows))
        checked.append((fix.observed_at, identifier, fix))
    checked.sort(key=lambda item: (item[0], item[1]))
    return AISContextResult(
        fixes=tuple(item[2] for item in checked),
        track_ids=tuple(item[1] for item in checked),
        complete=True, inspected_rows=len(rows),
    )


def load_ais_context_db(
    db: object,
    mmsi: str,
    occurred_at: datetime,
    *,
    before_minutes: int = 30,
    after_minutes: int = 90,
    max_rows: int = 256,
) -> AISContextResult:
    """SELECT-only adapter for an explicitly READ ONLY PostgreSQL transaction.

    Reject SQLite, read-write sessions and ambiguous transaction state.
    no_autoflush prevents SQLAlchemy from flushing unrelated pending writes
    before either the read-only check or the SELECT. Never opens a session,
    changes transaction mode, commits, or touches the operational scheduler.
    """
    if db.get_bind().dialect.name != "postgresql":
        raise ValueError("AIS context DB adapter requires PostgreSQL")
    from sqlalchemy import text
    from core.db.models import VesselTrackDB

    with db.no_autoflush:
        readonly = db.execute(text("SHOW transaction_read_only")).scalar_one()
        if str(readonly).strip().lower() not in {"on", "true"}:
            raise ValueError("AIS context requires a READ ONLY transaction")

        def fetch(mmsi: str, start: datetime, end: datetime, limit: int):
            # Canonical vessel_tracks.ts stores naive UTC; retain receipt
            # chronology separately when converting each returned row.
            return (db.query(VesselTrackDB)
                    .filter(VesselTrackDB.mmsi == mmsi,
                            VesselTrackDB.ts >= start.replace(tzinfo=None),
                            VesselTrackDB.ts <= end.replace(tzinfo=None))
                    .order_by(VesselTrackDB.ts, VesselTrackDB.id)
                    .limit(limit).all())

        return load_ais_context(
            mmsi, occurred_at, fetch, before_minutes=before_minutes,
            after_minutes=after_minutes, max_rows=max_rows,
        )
