# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M4.1/M4.3: pure AIS-integrity replay classifiers."""
from __future__ import annotations

import pytest

from core.intel.ais_integrity_replay import (
    classify,
    classify_dark_zone_entry,
    classify_gap,
    classify_impossible_speed,
)


def test_healthy_surrounding_coverage_is_a_vessel_gap():
    label, confidence = classify_gap(
        silence_duration_min=45,
        nearby_vessels_reporting_before=12,
        nearby_vessels_reporting_after=11,
        local_reporting_ratio=0.9,
    )
    assert label == "vessel_gap"
    assert 0.4 <= confidence <= 0.7


def test_a_feed_wide_outage_is_a_coverage_gap_not_hundreds_of_vessel_gaps():
    """docs/fixes.md M4.3: a feed-wide AIS outage must NOT create hundreds
    of vessel-specific gaps -- nearby traffic also disappeared."""
    label, confidence = classify_gap(
        silence_duration_min=45,
        nearby_vessels_reporting_before=12,
        nearby_vessels_reporting_after=1,
        local_reporting_ratio=0.08,
    )
    assert label == "coverage_gap"
    assert 0.0 <= confidence <= 0.1


def test_gap_classification_never_takes_a_vessel_type_parameter():
    """M4.3: vessel class becomes a contextual feature only -- satisfied
    here by construction, there is no vessel_type parameter to exclude
    on at all."""
    import inspect

    assert "vessel_type" not in inspect.signature(classify_gap).parameters


def test_a_fast_cargo_ship_is_flagged_the_same_as_any_other_type():
    label, confidence = classify_impossible_speed(
        implied_speed_kn=65, vessel_type="cargo", time_delta_s=30,
    )
    assert label == "position_anomaly"
    assert 0.5 <= confidence <= 0.8

    # Same speed, different declared type -- must classify identically.
    same_label, same_confidence = classify_impossible_speed(
        implied_speed_kn=65, vessel_type="fishing", time_delta_s=30,
    )
    assert same_label == label
    assert same_confidence == confidence


def test_a_plausible_speed_is_not_alertable():
    label, confidence = classify_impossible_speed(
        implied_speed_kn=18, vessel_type="cargo", time_delta_s=30,
    )
    assert label == "not_alertable"
    assert confidence == 0.0


def test_dark_zone_entry_is_only_ever_a_candidate_never_confirmed():
    """docs/fixes.md: an AIS gap is not proof of intentional disabling."""
    label, confidence = classify_dark_zone_entry(
        mmsi="209999000", zone="known_dark_fleet_corridor", prior_gap=True,
    )
    assert label == "spoofing_candidate"
    assert 0.3 <= confidence <= 0.6


def test_dark_zone_entry_outside_a_known_corridor_is_not_alertable():
    label, confidence = classify_dark_zone_entry(
        mmsi="209999000", zone="open_ocean", prior_gap=True,
    )
    assert label == "not_alertable"
    assert confidence == 0.0


def test_classify_dispatches_on_the_kind_field():
    label, _ = classify({
        "kind": "gap", "silence_duration_min": 45,
        "nearby_vessels_reporting_before": 12, "nearby_vessels_reporting_after": 11,
        "local_reporting_ratio": 0.9,
    })
    assert label == "vessel_gap"


def test_classify_raises_for_an_unimplemented_kind():
    with pytest.raises(KeyError):
        classify({"kind": "identity_swap"})
