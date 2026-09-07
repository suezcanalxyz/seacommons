# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from core.radio.burst import RadioBurst


def persist_radio_burst(db, burst: RadioBurst):
    from core.db.models import RadioBurstDB

    row = db.query(RadioBurstDB).filter_by(burst_id=burst.burst_id).one_or_none()
    if row is not None:
        return row
    row = RadioBurstDB(
        burst_id=burst.burst_id,
        physical_lineage=burst.physical_lineage,
        frequency_hz=burst.frequency_hz,
        started_at=burst.started_at,
        ended_at=burst.ended_at,
        sample_count=burst.sample_count,
        peak_signal_db=burst.peak_signal_db,
        mean_signal_db=burst.mean_signal_db,
    )
    db.add(row)
    db.flush()
    return row


def correlate_and_persist_recent(db, burst: RadioBurst, *, window_seconds: float = 5.0):
    from datetime import timedelta
    from core.db.models import RadioBurstDB, RadioEventDB
    from core.radio.burst import RadioBurst as Burst, correlate_bursts

    lower = burst.started_at - timedelta(seconds=float(window_seconds))
    upper = burst.started_at + timedelta(seconds=float(window_seconds))
    rows = (
        db.query(RadioBurstDB)
        .filter(RadioBurstDB.frequency_hz == burst.frequency_hz)
        .filter(RadioBurstDB.started_at >= lower)
        .filter(RadioBurstDB.started_at <= upper)
        .all()
    )
    bursts = tuple(Burst(
        row.burst_id, row.physical_lineage, row.frequency_hz,
        row.started_at, row.ended_at, row.sample_count,
        row.peak_signal_db, row.mean_signal_db,
    ) for row in rows)
    event = correlate_bursts(bursts, window_seconds=window_seconds)
    if event.independent_receivers < 2:
        return None
    saved = db.query(RadioEventDB).filter_by(event_id=event.event_id).one_or_none()
    if saved is None:
        saved = RadioEventDB(
            event_id=event.event_id, frequency_hz=event.frequency_hz,
            started_at=event.started_at, ended_at=event.ended_at,
            independent_receivers=event.independent_receivers,
            physical_lineages=list(event.physical_lineages), burst_ids=list(event.burst_ids),
            confidence=event.confidence,
        )
        db.add(saved)
        db.flush()
    return saved
