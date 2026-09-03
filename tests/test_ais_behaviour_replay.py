# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M4.1: pure AIS-behaviour replay classifiers."""
from __future__ import annotations

import pytest

from core.intel.ais_behaviour_replay import (
    classify,
    classify_ngo_search_pattern,
    classify_rescue_cluster,
    classify_sudden_stop,
)


def test_sudden_stop_is_a_low_confidence_cue_not_a_high_confidence_alert():
    label, confidence = classify_sudden_stop(
        previous_speed_kn=8.2, current_speed_kn=0.2, in_port_exclusion_zone=False,
    )
    assert label == "cue"
    assert 0.2 <= confidence <= 0.5


def test_sudden_stop_in_a_port_exclusion_zone_is_not_alertable():
    label, confidence = classify_sudden_stop(
        previous_speed_kn=6.0, current_speed_kn=0.0, in_port_exclusion_zone=True,
    )
    assert label == "not_alertable"
    assert confidence == 0.0


def test_sudden_stop_requires_a_real_underway_to_stopped_transition():
    # Already slow before -- not a "sudden" stop.
    label, _ = classify_sudden_stop(
        previous_speed_kn=1.0, current_speed_kn=0.2, in_port_exclusion_zone=False,
    )
    assert label == "not_alertable"


def test_rescue_cluster_is_never_more_than_possible():
    label, confidence = classify_rescue_cluster(
        vessel_count=3, min_distance_nm=2.1, positions_fresh=True, converging=True,
    )
    assert label == "possible_rescue_cluster"
    assert 0.4 <= confidence <= 0.7


def test_rescue_cluster_inside_a_port_is_not_alertable():
    """docs/prompt.md hard negative: NGO vessels clustered in port aren't
    a rescue operation."""
    label, confidence = classify_rescue_cluster(
        vessel_count=4, min_distance_nm=1.5, positions_fresh=False, converging=False, in_port=True,
    )
    assert label == "not_alertable"
    assert confidence == 0.0


def test_rescue_cluster_with_stale_positions_is_not_alertable():
    label, _ = classify_rescue_cluster(
        vessel_count=3, min_distance_nm=1.0, positions_fresh=False, converging=True,
    )
    assert label == "not_alertable"


def test_ngo_search_pattern_requires_a_known_sar_role():
    label, confidence = classify_ngo_search_pattern(
        fix_count=14, window_minutes=90, turn_count=6, known_operational_role="sar_ngo",
    )
    assert label == "ngo_search_pattern"
    assert 0.5 <= confidence <= 0.8


def test_ngo_search_pattern_from_an_unknown_vessel_is_not_alertable():
    """The same course-change signature from a vessel with no known SAR
    role is exactly what the spoofing/gap detectors flag instead."""
    label, _ = classify_ngo_search_pattern(
        fix_count=14, window_minutes=90, turn_count=6, known_operational_role="",
    )
    assert label == "not_alertable"


def test_ngo_search_pattern_needs_enough_track_history():
    label, _ = classify_ngo_search_pattern(
        fix_count=2, window_minutes=90, turn_count=6, known_operational_role="sar_ngo",
    )
    assert label == "not_alertable"


def test_classify_dispatches_on_the_kind_field():
    label, _ = classify({
        "kind": "sudden_stop", "previous_speed_kn": 8.0, "current_speed_kn": 0.1,
        "in_port_exclusion_zone": False,
    })
    assert label == "cue"


def test_classify_raises_for_an_unimplemented_kind():
    """vessel_loiter has no fixture/classifier yet -- must fail loudly,
    never silently degrade to a fabricated not_alertable."""
    with pytest.raises(KeyError):
        classify({"kind": "vessel_loiter"})
