# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M7.2: SAR candidate association.

Exit gate, verbatim: "Never emit 'dark vessel confirmed' from one
unmatched target."
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

from core.mda.sar_association import (
    CounterCandidate,
    SarAssociation,
    associate_candidate,
    propagate_ais_state,
)

_T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def test_propagation_holds_position_without_course_or_speed():
    state = propagate_ais_state(
        last_lat=35.5, last_lon=14.1, last_observed_at=_T0,
        target_time=_T0 + timedelta(hours=2),
    )
    assert state.lat == 35.5 and state.lon == 14.1
    assert state.elapsed_s == 7200


def test_propagation_moves_the_position_along_course_and_speed():
    state = propagate_ais_state(
        last_lat=35.5, last_lon=14.1, last_observed_at=_T0,
        target_time=_T0 + timedelta(hours=1),
        course_deg=90.0, speed_kn=10.0,  # due east
    )
    assert state.lat == 35.5  # unchanged heading due east
    assert state.lon > 14.1  # moved east


def test_uncertainty_grows_with_elapsed_time():
    soon = propagate_ais_state(
        last_lat=35.5, last_lon=14.1, last_observed_at=_T0, target_time=_T0 + timedelta(minutes=10),
    )
    later = propagate_ais_state(
        last_lat=35.5, last_lon=14.1, last_observed_at=_T0, target_time=_T0 + timedelta(hours=6),
    )
    assert later.uncertainty_m > soon.uncertainty_m


def test_uncertainty_grows_symmetrically_backward_in_time():
    """A scene acquired before the last AIS fix is exactly as uncertain as
    one acquired after it."""
    before = propagate_ais_state(
        last_lat=35.5, last_lon=14.1, last_observed_at=_T0, target_time=_T0 - timedelta(hours=2),
    )
    after = propagate_ais_state(
        last_lat=35.5, last_lon=14.1, last_observed_at=_T0, target_time=_T0 + timedelta(hours=2),
    )
    assert before.uncertainty_m == after.uncertainty_m


def test_a_detection_at_the_propagated_position_scores_high_confidence():
    propagated = propagate_ais_state(
        last_lat=35.5, last_lon=14.1, last_observed_at=_T0, target_time=_T0 + timedelta(minutes=5),
    )
    result = associate_candidate(
        scene_id="S1A_20260901", acquired_at=_T0 + timedelta(minutes=5),
        candidate_detection_id="det-1",
        detection_lat=propagated.lat, detection_lon=propagated.lon,
        propagated=propagated,
    )
    assert result.association_confidence > 0.5


def test_a_distant_detection_scores_low_confidence():
    propagated = propagate_ais_state(
        last_lat=35.5, last_lon=14.1, last_observed_at=_T0, target_time=_T0 + timedelta(minutes=5),
    )
    result = associate_candidate(
        scene_id="S1A_20260901", acquired_at=_T0 + timedelta(minutes=5),
        candidate_detection_id="det-2",
        detection_lat=40.0, detection_lon=20.0,  # far away
        propagated=propagated,
    )
    assert result.association_confidence < 0.1


def test_exit_gate_confidence_never_reaches_full_certainty_even_for_a_perfect_match():
    """Never emit 'dark vessel confirmed' from one unmatched target --
    even a distance of exactly zero must not read as certainty."""
    propagated = propagate_ais_state(
        last_lat=35.5, last_lon=14.1, last_observed_at=_T0, target_time=_T0,
    )
    result = associate_candidate(
        scene_id="S1A_20260901", acquired_at=_T0, candidate_detection_id="det-3",
        detection_lat=propagated.lat, detection_lon=propagated.lon, propagated=propagated,
    )
    assert result.association_confidence <= 0.75


def test_exit_gate_the_result_type_has_no_confirmed_or_status_field():
    """Structural proof: this type cannot represent 'confirmed' at all."""
    field_names = {f.name for f in dataclasses.fields(SarAssociation)}
    assert "confirmed" not in field_names
    assert "status" not in field_names
    assert "verdict" not in field_names


def test_result_carries_every_m7_2_required_field():
    propagated = propagate_ais_state(
        last_lat=35.5, last_lon=14.1, last_observed_at=_T0, target_time=_T0,
    )
    counter = (CounterCandidate(label="vessel:222000222", distance_to_predicted_area_m=900.0),)
    result = associate_candidate(
        scene_id="S1A_20260901", acquired_at=_T0, candidate_detection_id="det-4",
        detection_lat=35.51, detection_lon=14.11, propagated=propagated,
        counter_candidates=counter,
    )
    for field_name in (
        "scene_id", "acquired_at", "candidate_detection_id",
        "distance_to_predicted_area_m", "association_method",
        "association_confidence", "counter_candidates", "algorithm_version",
    ):
        assert hasattr(result, field_name)
    assert result.counter_candidates == counter
    assert result.algorithm_version
