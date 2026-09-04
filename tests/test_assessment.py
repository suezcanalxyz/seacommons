# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/prompt.md Phase 1/12 -- case-specific EventAssessment.

Two events of the same type must be able to produce different
interpretation text; an unhandled kind must return None, never generic
prose from event.type.
"""
from __future__ import annotations

from core.intel.assessment import build_assessment


def test_not_under_command_assessment_uses_the_actual_evidence():
    result = build_assessment({
        "ais_nav_status_kind": "not_under_command",
        "detection_reason": "Flagged after 4 report(s) over 780s (rule: ≥3 reports and ≥600s sustained).",
        "in_jamming_zone": False,
    })
    assert result is not None
    assert result.observation == (
        "Flagged after 4 report(s) over 780s (rule: ≥3 reports and ≥600s sustained)."
    )
    assert "not under command" in result.interpretation
    assert "not confirmation of mechanical failure" in result.interpretation
    assert "GNSS interference" not in result.interpretation
    assert result.evidence_level == "observed"
    assert 0.0 <= result.confidence <= 1.0
    assert result.caveats
    assert result.classification_version


def test_two_not_under_command_events_produce_different_interpretations():
    """The literal Phase 12 requirement: same type, different evidence,
    different interpretation text -- not the same canned sentence."""
    plain = build_assessment({
        "ais_nav_status_kind": "not_under_command",
        "detection_reason": "Flagged after 3 report(s) over 600s (rule: ≥3 reports and ≥600s sustained).",
        "in_jamming_zone": False,
    })
    jammed = build_assessment({
        "ais_nav_status_kind": "not_under_command",
        "detection_reason": "Flagged after 6 report(s) over 1400s (rule: ≥3 reports and ≥600s sustained).",
        "in_jamming_zone": True,
    })
    assert plain.observation != jammed.observation
    assert plain.interpretation != jammed.interpretation
    assert "GNSS interference" in jammed.interpretation
    assert "GNSS interference" not in plain.interpretation
    assert jammed.confidence > plain.confidence
    assert "gnss_jamming_zone_overlap" in jammed.confidence_basis
    assert "gnss_jamming_zone_overlap" not in plain.confidence_basis


def test_aground_assessment_is_distinct_from_not_under_command():
    aground = build_assessment({
        "ais_nav_status_kind": "aground",
        "detection_reason": "Flagged after 2 report(s) over 200s (rule: ≥2 reports and ≥180s sustained).",
    })
    assert aground is not None
    assert "aground" in aground.interpretation
    assert aground.recommended_action == "published_operational_incident"
    assert aground.confidence > 0.5


def test_restricted_manoeuvrability_states_the_dredger_caveat():
    result = build_assessment({"ais_nav_status_kind": "restricted_manoeuvrability"})
    assert result is not None
    assert any("dredger" in c for c in result.caveats)
    assert result.confidence < 0.5  # weak signal -- no vessel-role check yet


def test_unhandled_kind_returns_none_not_generic_prose():
    assert build_assessment({"ais_nav_status_kind": "some_future_kind"}) is None
    assert build_assessment({}) is None


def test_build_assessment_accepts_an_event_object_not_just_a_dict():
    from core.intel.store import IntelEvent

    event = IntelEvent(
        type="vessel_incident",
        metadata={"ais_nav_status_kind": "aground", "detection_reason": "x"},
    )
    result = build_assessment(event)
    assert result is not None
    assert result.rule_ids == ["aground_sustained"]


def test_sudden_stop_assessment_is_derived_from_persistence_evidence():
    result = build_assessment({
        "spike_type": "sudden_stop",
        "stop_samples": 4,
        "stop_persistence_s": 720,
        "stop_displacement_nm": 0.02,
        "nav_status": 0,
    })
    assert result is not None
    assert result.evidence_level == "derived"
    assert "held" in result.observation
    assert any("speed transition" in caveat.lower() for caveat in result.caveats)


def test_rescue_cluster_needs_convergence_and_distress_for_corroborated_assessment():
    result = build_assessment({
        "spike_type": "rescue_cluster",
        "cluster_size": 3,
        "converging": True,
        "positions_max_age_s": 120,
        "near_active_distress": "case-1",
        "closing_nm": -0.5,
    })
    assert result is not None
    assert result.evidence_level == "corroborated"
    assert "rescue" in result.interpretation.lower()
    assert result.confidence > 0.5


def test_vessel_specific_ais_gap_is_derived_not_proof_of_intent():
    result = build_assessment({
        "anomaly_type": "gap",
        "anomaly_evidence": {
            "silent_seconds": 1800,
            "nearby_vessels_before": 4,
            "nearby_vessels_after": 4,
            "local_reporting_ratio": 1.0,
        },
    })
    assert result is not None
    assert result.evidence_level == "derived"
    assert "not proof of intent" in result.interpretation.lower()


def test_coverage_gap_is_context_not_vessel_intent():
    result = build_assessment({
        "anomaly_type": "coverage_gap",
        "anomaly_evidence": {
            "silent_seconds": 1800,
            "nearby_vessels_before": 4,
            "nearby_vessels_after": 0,
            "local_reporting_ratio": 0.0,
        },
    })
    assert result is not None
    assert result.evidence_level == "derived"
    assert "coverage" in result.interpretation.lower()
    assert result.recommended_action == "treat_as_coverage_context"
