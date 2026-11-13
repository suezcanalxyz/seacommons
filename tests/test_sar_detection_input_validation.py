# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reject malformed SAR evidence before it can corroborate a maritime episode.

Pure unit tests: no database, credentials, provider calls or production writes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.intel.satellite_observation import (
    _valid_mmsi,
    materialize_sar_detections,
)


ACQUIRED = "2026-09-17T10:15:00Z"


def _cue(**changes):
    detection = {
        "lat": 35.53, "lon": 14.15, "timestamp": ACQUIRED,
        "matched": True, "mmsi": "211879870",
    }
    detection.update(changes)
    return {"gfw_sar_detections": [detection]}


def _materialize(**changes):
    return materialize_sar_detections(
        incident_id="sar-validation-test",
        cue=_cue(**changes),
        expected_mmsi="211879870",
        episode_id="episode:sar-validation-test",
    )


@pytest.mark.parametrize("lat,lon", [
    (float("nan"), 14.15),
    (35.53, float("inf")),
    (float("-inf"), 14.15),
    (91, 14.15),
    (-91, 14.15),
    (35.53, 181),
    (35.53, -181),
    ("not-a-coordinate", 14.15),
    (True, 14.15),
    (35.53, False),
    (None, 14.15),
])
def test_bad_coordinates_never_create_satellite_evidence(lat, lon):
    assert _materialize(lat=lat, lon=lon) == []


@pytest.mark.parametrize("timestamp", [
    None, "", "not-a-time", "2026-09-17", "2026-09-17T10:15:00",
])
def test_missing_or_unqualified_acquisition_never_defaults_to_now(timestamp):
    assert _materialize(timestamp=timestamp) == []


def test_future_acquisition_does_not_create_evidence():
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert _materialize(timestamp=future) == []


@pytest.mark.parametrize("matched", ["true", "false", "1", 1, None, False])
def test_non_boolean_provider_match_never_promotes_to_strong(matched):
    observations = _materialize(matched=matched)
    assert len(observations) == 1
    assert observations[0].association_status == "unmatched_candidate"
    assert observations[0].episode_id is None
    assert observations[0].evidence_status == "contextual"


def test_valid_provider_match_retains_strong_association():
    observations = _materialize()
    assert len(observations) == 1
    assert observations[0].association_status == "strong"
    assert observations[0].episode_id == "episode:sar-validation-test"
    assert observations[0].footprint == {
        "type": "Point", "coordinates": [14.15, 35.53],
    }
    assert observations[0].acquisition_time == "2026-09-17T10:15:00+00:00"


def test_equivalent_utc_timestamps_produce_same_evidence_id():
    z = _materialize(timestamp="2026-09-17T10:15:00Z")
    offset = _materialize(timestamp="2026-09-17T12:15:00+02:00")
    assert z[0].observation_id == offset[0].observation_id


def test_unicode_digits_cannot_be_used_as_mmsi():
    assert _valid_mmsi("٢١١٨٧٩٨٧٠") == ""
    assert _valid_mmsi("211879870") == "211879870"
