"""Fail-closed public projection for corrupted OpenDrift samples.

No database, external forcing download, or production state is required.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from core.live.projection import (
    _current_trajectory_estimate,
    _is_publishable_live_drift,
)


def _trajectory() -> dict:
    return {
        "geometry": {
            "type": "LineString",
            "coordinates": [[14.0, 35.0], [15.0, 36.0]],
        },
        "properties": {
            "timestamps_utc": ["2026-08-01T10:00:00Z", "2026-08-01T12:00:00Z"],
            "speed_ms": [0.2, 0.3],
        },
    }


def _drift() -> dict:
    return {
        "status": "completed",
        "metadata": {
            "model": "OpenDrift OceanDrift",
            "forcing_quality": "observed-spatiotemporal",
            "operational_use": True,
        },
        "trajectory": _trajectory(),
    }


def _estimate(trajectory: dict, *, hour: int = 11):
    return _current_trajectory_estimate(
        trajectory,
        event_timestamp="2026-08-01T09:00:00Z",
        now=datetime(2026, 8, 1, hour, tzinfo=UTC),
    )


def test_valid_drift_interpolates_and_remains_publishable():
    trajectory = _trajectory()
    assert _is_publishable_live_drift(_drift())
    estimate = _estimate(trajectory)
    assert estimate is not None
    assert estimate["geometry"]["coordinates"] == [14.5, 35.5]
    assert estimate["properties"]["trajectory_state"] == "interpolated"
    assert _estimate(trajectory, hour=9)["geometry"]["coordinates"] == [14.0, 35.0]
    assert _estimate(trajectory, hour=13)["geometry"]["coordinates"] == [15.0, 36.0]


@pytest.mark.parametrize("bad_point", [
    [181.0, 35.0], [14.0, -91.0], [float("nan"), 35.0],
    [14.0, float("inf")], [True, 35.0], ["14.0", 35.0],
    [14.0], None, {"lon": 14.0, "lat": 35.0}, [10**1000, 35.0],
])
def test_bad_coordinate_anywhere_suppresses_entire_drift(bad_point):
    drift = _drift()
    drift["trajectory"]["geometry"]["coordinates"][1] = bad_point
    assert _is_publishable_live_drift(drift) is False
    assert _estimate(drift["trajectory"], hour=9) is None


@pytest.mark.parametrize("bad_times", [
    ["2026-08-01T10:00:00Z", "2026-08-01T10:00:00Z"],
    ["2026-08-01T12:00:00Z", "2026-08-01T10:00:00Z"],
    ["2026-08-01T10:00:00Z", "invalid"],
    ["2026-08-01T10:00:00Z"],
])
def test_unordered_invalid_or_missing_timestamps_suppress_drift(bad_times):
    drift = _drift()
    drift["trajectory"]["properties"]["timestamps_utc"] = bad_times
    assert _is_publishable_live_drift(drift) is False
    assert _estimate(drift["trajectory"]) is None


@pytest.mark.parametrize("bad_speed", [float("nan"), float("inf"), -0.1, True, "0.2", None, 10**1000])
def test_invalid_sample_speed_suppresses_public_drift(bad_speed):
    drift = _drift()
    drift["trajectory"]["properties"]["speed_ms"][0] = bad_speed
    assert _is_publishable_live_drift(drift) is False
    # The current estimate validates spatial/temporal samples independently;
    # the public publication gate also requires physically valid speeds.
    assert _estimate(drift["trajectory"]) is not None


def test_invalid_geometry_type_does_not_raise():
    drift = _drift()
    drift["trajectory"]["geometry"] = {"type": "Point", "coordinates": [14.0, 35.0]}
    assert _is_publishable_live_drift(drift) is False
    assert _estimate(drift["trajectory"]) is None


def test_naive_timestamps_interpreted_as_utc_without_local_timezone_dependency():
    trajectory = _trajectory()
    trajectory["properties"]["timestamps_utc"] = [
        "2026-08-01T10:00:00", "2026-08-01T12:00:00",
    ]
    assert _estimate(trajectory)["geometry"]["coordinates"] == [14.5, 35.5]


def test_validation_never_mutates_persisted_drift_payload():
    drift = _drift()
    drift["trajectory"]["geometry"]["coordinates"][0] = [float("nan"), 35.0]
    original = deepcopy(drift)
    assert _is_publishable_live_drift(drift) is False
    assert _estimate(drift["trajectory"]) is None
    assert drift == original or (
        # NaN is intentionally not equal to itself; compare every other field.
        drift["trajectory"]["properties"] == original["trajectory"]["properties"]
        and drift["metadata"] == original["metadata"]
        and drift["trajectory"]["geometry"]["coordinates"][1]
        == original["trajectory"]["geometry"]["coordinates"][1]
    )
