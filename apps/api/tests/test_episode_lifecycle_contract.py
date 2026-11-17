from datetime import datetime, timedelta, timezone

import pytest

from core.intel.episode_lifecycle import (
    elapsed_seconds,
    play_eligible,
    reconcile_gap,
    visible_in_live,
)

T0 = datetime(2026, 11, 17, 10, tzinfo=timezone.utc)


def test_play_promotion_after_exactly_24h_even_if_active():
    assert not play_eligible(detected_at=T0, now=T0 + timedelta(hours=24, seconds=-1))
    assert play_eligible(detected_at=T0, now=T0 + timedelta(hours=24))
    assert visible_in_live(detected_at=T0, status="active", now=T0 + timedelta(hours=53))
    assert not visible_in_live(detected_at=T0, status="resolved", now=T0 + timedelta(hours=53))


def test_running_gap_duration_and_verified_reappearance():
    gap = {
        "episode_id": "gap-1",
        "status": "active",
        "origin": {"observed_at": T0, "coordinates": [12.0, 35.0], "observation_id": "a"},
        "endpoint": None,
        "observation_ids": ["a"],
    }
    assert elapsed_seconds(started_at=T0, ended_at=None, now=T0 + timedelta(hours=25)) == 90000
    assert reconcile_gap(gap, observation_id="a", observed_at=T0, coordinates=(12, 35)) == gap
    assert reconcile_gap(gap, observation_id="old", observed_at=T0 - timedelta(seconds=1), coordinates=(12, 35)) == gap
    assert reconcile_gap(gap, observation_id="b", observed_at=T0 + timedelta(hours=53), coordinates=(13, 36)) == gap
    assert reconcile_gap(gap, observation_id="b", observed_at=T0 + timedelta(hours=53), coordinates=(13, 36), identity_validated=True) == gap
    assert reconcile_gap(gap, observation_id="b", observed_at=T0 + timedelta(hours=53), coordinates=(13, 36), source_validated=True) == gap
    closed = reconcile_gap(gap, observation_id="b", observed_at=T0 + timedelta(hours=53), coordinates=(13, 36), identity_validated=True, source_validated=True)
    assert gap["endpoint"] is None
    assert closed["episode_id"] == "gap-1"
    assert closed["status"] == "resolved"
    assert closed["endpoint"]["coordinates"] == [13, 36]
    assert elapsed_seconds(started_at=T0, ended_at=closed["ended_at"], now=T0 + timedelta(hours=60)) == 53 * 3600
    assert reconcile_gap(closed, observation_id="b", observed_at=T0 + timedelta(hours=53), coordinates=(13, 36)) == closed
    assert play_eligible(detected_at=T0, now=T0 + timedelta(hours=53))


def test_invalid_endpoint_and_negative_duration():
    gap = {"status": "active", "origin": {"observed_at": T0}}
    with pytest.raises(ValueError):
        reconcile_gap(gap, observation_id="b", observed_at=T0 + timedelta(hours=1), coordinates=(200, 0), identity_validated=True, source_validated=True)
    with pytest.raises(ValueError):
        elapsed_seconds(started_at=T0, ended_at=T0 - timedelta(seconds=1), now=T0)
