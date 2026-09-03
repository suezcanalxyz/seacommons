# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M1.1 exit gate: replaying the same raw fixture twice
produces one observation and identical normalized output."""
from __future__ import annotations

from dataclasses import asdict

from core.db.session import session_scope
from core.intel.source_observation import get_observation, observation_id, record_observation


def _record(db, **overrides):
    kwargs = dict(
        service="humanitarian",
        lane="distress",
        observation_type="source_post",
        source_name="alarm_phone",
        source_policy="official_api",
        source_id="tweet-12345",
        observed_at="2026-09-03T10:00:00+00:00",
        raw_payload="🆘 30 people in distress off Libya",
        source_url="https://x.com/i/web/status/12345",
        lat=33.9,
        lon=13.2,
        location_precision="reported_exact",
        uncertainty_m=500.0,
        subject_refs=["mmsi:209888000"],
        provenance={"tracked_account": "alarm_phone"},
    )
    kwargs.update(overrides)
    return record_observation(db, **kwargs)


def test_observation_id_is_deterministic_from_the_delivery_key():
    assert observation_id("alarm_phone", "tweet-12345") == observation_id("alarm_phone", "tweet-12345")
    assert observation_id("alarm_phone", "tweet-12345") != observation_id("alarm_phone", "tweet-99999")
    assert observation_id("alarm_phone", "tweet-12345") != observation_id("sea_watch", "tweet-12345")


def test_replaying_the_same_fixture_twice_produces_one_observation_and_identical_output():
    with session_scope() as db:
        first = _record(db)
        db.flush()
        assert first.replayed is False

        second = _record(db)
        assert second.replayed is True

        # Identical normalized output except the one field that legitimately
        # differs (replayed): everything the fixture actually describes is
        # exactly the same both times.
        first_dict = asdict(first)
        second_dict = asdict(second)
        del first_dict["replayed"]
        del second_dict["replayed"]
        assert first_dict == second_dict
        assert first.observation_id == second.observation_id

    # Row count assertion via a fresh session, independent of the ORM identity map.
    with session_scope() as db2:
        from core.db.models import SourceObservationDB

        count = db2.query(SourceObservationDB).filter(
            SourceObservationDB.source_name == "alarm_phone",
            SourceObservationDB.source_id == "tweet-12345",
        ).count()
        assert count == 1


def test_a_different_source_id_creates_a_distinct_observation():
    with session_scope() as db:
        first = _record(db, source_id="tweet-A")
        second = _record(db, source_id="tweet-B")
        assert first.observation_id != second.observation_id
        assert first.replayed is False
        assert second.replayed is False


def test_record_preserves_provenance_geometry_and_subject_refs():
    with session_scope() as db:
        obs = _record(db, source_id="tweet-preserve")
        assert obs.lat == 33.9
        assert obs.lon == 13.2
        assert obs.location_precision == "reported_exact"
        assert obs.uncertainty_m == 500.0
        assert obs.subject_refs == ["mmsi:209888000"]
        assert obs.provenance == {"tracked_account": "alarm_phone"}
        assert obs.raw_payload_hash  # a real hash, not blank
        assert obs.schema_version == 1


def test_get_observation_returns_none_for_an_unknown_id():
    with session_scope() as db:
        assert get_observation(db, "obs:doesnotexist") is None


def test_get_observation_finds_a_previously_recorded_row():
    with session_scope() as db:
        recorded = _record(db, source_id="tweet-lookup")
        found = get_observation(db, recorded.observation_id)
        assert found is not None
        assert found.observation_id == recorded.observation_id
        assert found.source_id == "tweet-lookup"
