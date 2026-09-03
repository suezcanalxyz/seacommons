# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M1.2: the official sanctions-list adapter.

Exercises core.mda.identity._record_sanctions_observations directly
(the same helper refresh_sanctions() calls on every real list refresh)
rather than mocking the OFAC/OpenSanctions HTTP downloads.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.db.models import SourceObservationDB
from core.db.session import session_scope
from core.intel.source_observation import observation_id
from core.mda.identity import _record_sanctions_observations


def _row(**overrides):
    row = {
        "source_list": "OFAC_SDN",
        "name": "MV SHADOW STAR",
        "name_upper": "MV SHADOW STAR",
        "imo": "9123456",
        "mmsi": None,
        "program": "IRAN",
        "listed_on": "2024-01-15",
        "updated_at": datetime.now(timezone.utc),
    }
    row.update(overrides)
    return row


def test_each_sanctions_row_records_a_source_observation():
    _record_sanctions_observations([_row()])

    obs_id = observation_id("OFAC_SDN", "9123456")
    with session_scope() as db:
        row = db.query(SourceObservationDB).filter(
            SourceObservationDB.source_name == "OFAC_SDN",
            SourceObservationDB.source_id == "9123456",
        ).one()
        assert row.observation_id == obs_id
        assert row.service == "maritime"
        assert row.lane == "intelligence"
        assert row.observation_type == "sanctions_list_match"
        assert row.source_policy == "official_open"
        assert row.provenance["program"] == "IRAN"


def test_identifier_falls_back_to_mmsi_then_name(monkeypatch):
    mmsi_only = _row(imo=None, mmsi="273999000")
    _record_sanctions_observations([mmsi_only])
    with session_scope() as db:
        assert db.query(SourceObservationDB).filter(
            SourceObservationDB.source_name == "OFAC_SDN",
            SourceObservationDB.source_id == "273999000",
        ).count() == 1

    name_only = _row(imo=None, mmsi=None, name_upper="MV NO IDENTIFIERS")
    _record_sanctions_observations([name_only])
    with session_scope() as db:
        assert db.query(SourceObservationDB).filter(
            SourceObservationDB.source_name == "OFAC_SDN",
            SourceObservationDB.source_id == "MV NO IDENTIFIERS",
        ).count() == 1


def test_a_row_with_no_identifier_at_all_is_skipped_not_crashed():
    # Must not raise, and must not create a garbage row keyed by "".
    _record_sanctions_observations([_row(imo=None, mmsi=None, name_upper="")])
    with session_scope() as db:
        assert db.query(SourceObservationDB).filter(
            SourceObservationDB.source_id == ""
        ).count() == 0


def test_re_refreshing_an_unchanged_listing_does_not_duplicate():
    """The M1.1 idempotency contract applies here too: refresh_sanctions()
    runs on a schedule (daily), so an unchanged listing must not grow the
    table on every re-refresh."""
    row = _row()
    _record_sanctions_observations([row])
    _record_sanctions_observations([row])  # simulates the next day's refresh

    with session_scope() as db:
        assert db.query(SourceObservationDB).filter(
            SourceObservationDB.source_name == "OFAC_SDN",
            SourceObservationDB.source_id == "9123456",
        ).count() == 1


def test_opensanctions_and_ofac_rows_for_the_same_vessel_stay_distinct():
    """Two different lists asserting the same vessel is sanctioned are two
    independent pieces of evidence, not one -- different source_name means
    a different observation_id even for the same identifier."""
    _record_sanctions_observations([
        _row(source_list="OFAC_SDN", imo="9123456"),
        _row(source_list="OpenSanctions", imo="9123456"),
    ])
    with session_scope() as db:
        rows = db.query(SourceObservationDB).filter(
            SourceObservationDB.source_id == "9123456"
        ).all()
        assert {r.source_name for r in rows} == {"OFAC_SDN", "OpenSanctions"}
        assert len(rows) == 2


def test_a_broken_session_does_not_raise(monkeypatch):
    """Best-effort: refresh_sanctions()'s authoritative bulk_insert must
    never be put at risk by this batch failing."""
    def _boom(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("core.db.session.session_scope", _boom)
    _record_sanctions_observations([_row()])  # must not raise
