# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M4.3: the AIS gap reason-code feature.

Exit gate, verbatim: "synthetic/common port outage produces no
intentional-dark hypothesis; genuine isolated gap fixture remains
detectable independent of vessel class."
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone

from core.mda.coverage import CoverageBaseline
from core.mda.gap_reason import build_gap_reason


def _coverage(**overrides) -> CoverageBaseline:
    defaults = dict(
        mmsi="111000111",
        at=datetime.now(timezone.utc),
        source_health="healthy",
        expected_reporting_interval_s=60.0,
        local_receiver_density=12,
        neighbour_message_ratio=1.0,
        coast_distance_km=15.0,
        congestion="medium",
        jamming_context=0.05,
        preceding_track_density=6,
    )
    defaults.update(overrides)
    return CoverageBaseline(**defaults)


def test_exit_gate_synthetic_port_outage_produces_no_intentional_dark_hypothesis():
    """Many nearby vessels also went quiet (the same 'a feed-wide AIS
    outage must NOT create hundreds of vessel-specific gaps' fixture
    shape as ais-integ-neg-001) -- the cause is the reception environment,
    not this one vessel."""
    reason = build_gap_reason(
        gap_duration_s=45 * 60,
        nearby_vessels_reporting_before=12,
        nearby_vessels_reporting_after=1,
        coverage=_coverage(neighbour_message_ratio=0.08),
    )
    assert reason.hypothesis == "coverage_gap"
    assert reason.hypothesis != "intentional_dark_candidate"
    assert reason.confidence <= 0.1


def test_exit_gate_genuine_isolated_gap_remains_detectable():
    """Healthy surrounding coverage -- nearby vessels kept reporting
    normally through the same window -- so this vessel's own silence is
    plausibly deliberate, independent of what type of vessel it is."""
    reason = build_gap_reason(
        gap_duration_s=45 * 60,
        nearby_vessels_reporting_before=12,
        nearby_vessels_reporting_after=11,
        coverage=_coverage(),
    )
    assert reason.hypothesis == "vessel_gap"
    assert 0.4 <= reason.confidence <= 0.7


def test_build_gap_reason_has_no_vessel_type_parameter():
    """Structural proof of docs/fixes.md M4.3's 'vessel class becomes a
    contextual feature only' -- there is nothing here to gate on."""
    params = inspect.signature(build_gap_reason).parameters
    assert "vessel_type" not in params
    assert "ship_type" not in params


def test_reason_components_carry_every_m4_3_required_field():
    reason = build_gap_reason(
        gap_duration_s=3600,
        nearby_vessels_reporting_before=10,
        nearby_vessels_reporting_after=9,
        coverage=_coverage(),
        pre_gap_course=185.0,
        pre_gap_speed=6.5,
        post_gap_reappearance=True,
    )
    for field_name in (
        "gap_duration_s", "expected_messages", "coverage_ratio",
        "neighbour_message_ratio", "pre_gap_course", "pre_gap_speed",
        "post_gap_reappearance", "coast_distance_km", "jamming_context",
    ):
        assert hasattr(reason, field_name)
    assert reason.pre_gap_course == 185.0
    assert reason.pre_gap_speed == 6.5
    assert reason.post_gap_reappearance is True
    assert reason.coast_distance_km == 15.0
    assert reason.jamming_context == 0.05


def test_expected_messages_derives_from_the_coverage_reporting_interval():
    reason = build_gap_reason(
        gap_duration_s=600,  # 10 minutes
        nearby_vessels_reporting_before=10,
        nearby_vessels_reporting_after=9,
        coverage=_coverage(expected_reporting_interval_s=60.0),
    )
    assert reason.expected_messages == 10  # 600s / 60s per expected message


def test_expected_messages_is_none_when_the_interval_is_unknown():
    reason = build_gap_reason(
        gap_duration_s=600,
        nearby_vessels_reporting_before=10,
        nearby_vessels_reporting_after=9,
        coverage=_coverage(expected_reporting_interval_s=None),
    )
    assert reason.expected_messages is None


def test_no_prior_traffic_to_compare_against_is_not_a_zero_division():
    reason = build_gap_reason(
        gap_duration_s=3600,
        nearby_vessels_reporting_before=0,
        nearby_vessels_reporting_after=0,
        coverage=_coverage(local_receiver_density=0, neighbour_message_ratio=None),
    )
    assert reason.coverage_ratio == 0.0
    assert reason.hypothesis == "coverage_gap"
