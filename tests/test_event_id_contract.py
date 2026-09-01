# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/prompt.md P0 -- one lossless event-identifier contract.

Generated identifiers such as ``spoof:247384100:circular`` exceeded the
16-char intel_events.id column and were lost / truncated in production.
Every field that semantically stores an intel-event identity must be the
same width, and no code path may slice an identity to fit a column.
"""
from __future__ import annotations

import pathlib

from sqlalchemy import select

from core.db.models import (
    EVENT_ID_MAX_LENGTH,
    AlertEvent,
    AnomalyEvent,
    CaseIntelEventDB,
    DriftResultDB,
    ForensicEvent,
    IntelEventDB,
)
from core.db.session import session_scope

_LONG_IDS = [
    "vesselid:319775000",
    "spoof:247384100:circular",
    "acled:" + "9" * 40,
    ("x" * 32) + ":alpha",
    ("x" * 32) + ":bravo",
]


def _insert_intel(event_id: str) -> None:
    with session_scope() as db:
        db.add(IntelEventDB(
            id=event_id, timestamp_utc="2026-09-01T00:00:00+00:00",
            type="ais_anomaly", severity="high", title="t", source="SeaCommons MDA",
            meta={},
        ))


def test_intel_event_id_round_trips_exactly():
    for eid in _LONG_IDS:
        _insert_intel(eid)
    with session_scope() as db:
        stored = set(db.execute(select(IntelEventDB.id)).scalars())
    for eid in _LONG_IDS:
        assert eid in stored, eid


def test_two_ids_sharing_first_32_chars_stay_distinct():
    a = ("x" * 32) + ":alpha"
    b = ("x" * 32) + ":bravo"
    _insert_intel(a)
    _insert_intel(b)
    with session_scope() as db:
        rows = db.execute(
            select(IntelEventDB.id).where(IntelEventDB.id.in_([a, b]))
        ).scalars().all()
    assert set(rows) == {a, b}
    assert len(rows) == 2


def test_case_intel_event_link_preserves_the_full_identifier():
    eid = "spoof:247384100:circular"
    with session_scope() as db:
        db.add(CaseIntelEventDB(
            case_id="case-1", event_id=eid, role="contributing", linked_by="test"
        ))
    with session_scope() as db:
        got = db.execute(
            select(CaseIntelEventDB.event_id).where(CaseIntelEventDB.case_id == "case-1")
        ).scalar_one()
    assert got == eid


def test_drift_forensic_anomaly_alert_event_ids_preserve_full_identifier():
    long32 = "z" * 40
    with session_scope() as db:
        db.add(DriftResultDB(drift_id="d1", event_id="intel:spoof:247384100:circular"))
        db.add(ForensicEvent(
            event_id="forensic:" + long32, timestamp_utc="2026-09-01T00:00:00+00:00",
            classification="distress", confidence=0.5,
        ))
        db.add(AnomalyEvent(
            event_id="anomaly:" + long32, timestamp_utc="2026-09-01T00:00:00+00:00",
            anomaly_type="gap", sensor_source="ais", confidence=0.5,
        ))
        db.add(AlertEvent(
            event_id="alert:" + long32, timestamp_utc="2026-09-01T00:00:00+00:00",
        ))
    with session_scope() as db:
        assert db.execute(
            select(DriftResultDB.event_id).where(DriftResultDB.drift_id == "d1")
        ).scalar_one() == "intel:spoof:247384100:circular"
        assert db.execute(
            select(ForensicEvent.event_id).where(ForensicEvent.event_id == "forensic:" + long32)
        ).scalar_one() == "forensic:" + long32
        assert db.execute(
            select(AnomalyEvent.event_id).where(AnomalyEvent.event_id == "anomaly:" + long32)
        ).scalar_one() == "anomaly:" + long32
        assert db.execute(
            select(AlertEvent.event_id).where(AlertEvent.event_id == "alert:" + long32)
        ).scalar_one() == "alert:" + long32


def test_canonical_event_id_columns_share_one_width():
    widths = {
        "intel_events.id": IntelEventDB.__table__.c.id.type.length,
        "alert_events.event_id": AlertEvent.__table__.c.event_id.type.length,
        "anomaly_events.event_id": AnomalyEvent.__table__.c.event_id.type.length,
        "drift_results.event_id": DriftResultDB.__table__.c.event_id.type.length,
        "forensic_events.event_id": ForensicEvent.__table__.c.event_id.type.length,
        "case_intel_events.event_id": CaseIntelEventDB.__table__.c.event_id.type.length,
    }
    assert set(widths.values()) == {EVENT_ID_MAX_LENGTH}, widths
    assert EVENT_ID_MAX_LENGTH == 64


def test_no_event_identity_truncation_in_source():
    root = pathlib.Path(__file__).resolve().parents[1] / "apps" / "api" / "core"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if "[:32]" not in stripped and "[:16]" not in stripped:
                continue
            # identity variables only -- never time_utc / hashes / free text
            if any(tok in stripped for tok in ("eid[:32]", "wid[:32]", "event_id)[:32]",
                                               "i[:32] for i in linked_ids", "[:16]) for i")):
                offenders.append(f"{path.relative_to(root)}:{lineno}: {stripped}")
    assert not offenders, "event-identity truncation still present:\n" + "\n".join(offenders)
