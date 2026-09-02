# SPDX-License-Identifier: AGPL-3.0-or-later
"""core.intel.assessment -- case-specific EventAssessment (docs/prompt.md PHASE 1)."""
from __future__ import annotations

from core.intel.assessment import (
    CLASSIFICATION_VERSION,
    assess,
    assess_ais_gap,
    assess_humanitarian,
    assess_not_under_command,
    assess_rescue_cluster,
    assess_sudden_stop,
)


def test_two_nuc_events_produce_different_interpretations():
    brief = assess_not_under_command(reports=1, span_s=45, speed_kn=0.2, vessel_type="cargo")
    sustained = assess_not_under_command(reports=5, span_s=900, speed_kn=0.0, vessel_type="cargo")
    assert brief.observation != sustained.observation
    assert "1 report" in brief.observation and "5 reports" in sustained.observation
    assert brief.evidence_level == "single_observation"
    assert sustained.evidence_level == "sustained_observation"
    assert sustained.confidence > brief.confidence


def test_nuc_interpretation_carries_the_caveat_and_is_not_distress():
    a = assess_not_under_command(reports=4, span_s=780, speed_kn=0.3)
    assert "not confirmation of mechanical failure" in a.interpretation
    assert any("not independently confirmed" in c for c in a.caveats)


def test_nuc_with_jamming_is_contextual_not_a_confirmed_security_event():
    a = assess_not_under_command(reports=5, span_s=900, speed_kn=0.1, gnss_jamming=True)
    assert "GNSS interference" in a.interpretation
    assert "does not prove causation" in a.interpretation
    assert a.evidence_level == "multi_source"
    assert any("does not on its own make this a" in c for c in a.caveats)


def test_sudden_stop_one_sample_is_a_cue_not_an_alert():
    cue = assess_sudden_stop(
        prev_speed_kn=6.0, cur_speed_kn=0.3, samples=2, persistence_s=300,
        in_port_zone=False, in_anchorage=False,
    )
    real = assess_sudden_stop(
        prev_speed_kn=8.2, cur_speed_kn=0.2, samples=5, persistence_s=900,
        in_port_zone=False, in_anchorage=False, track_displacement_m=30,
    )
    assert cue.evidence_level == "single_observation"
    assert real.evidence_level == "sustained_observation"
    assert real.confidence > cue.confidence
    assert "cue" in cue.recommended_action.lower()


def test_sudden_stop_in_anchorage_lists_the_contradiction():
    a = assess_sudden_stop(
        prev_speed_kn=4.0, cur_speed_kn=0.0, samples=8, persistence_s=7200,
        in_port_zone=True, in_anchorage=True, nav_status=5,
    )
    assert any("anchorage" in c or "anchored" in c for c in a.contradicting_evidence)
    assert a.confidence < 0.6


def test_rescue_cluster_reports_the_numbers_and_never_calls_proximity_a_rescue():
    weak = assess_rescue_cluster(
        vessels=2, min_distance_nm=2.0, ngo_or_cg_present=True,
        positions_max_age_s=9000, converging=False,
    )
    strong = assess_rescue_cluster(
        vessels=3, min_distance_nm=1.4, ngo_or_cg_present=True,
        positions_max_age_s=300, converging=True, closing_rate_kn=2.1,
        active_distress_within_nm=6,
    )
    assert "2 vessels" in weak.observation and "3 vessels" in strong.observation
    assert weak.confidence < strong.confidence
    assert any("convergence" in c for c in weak.contradicting_evidence)
    assert strong.evidence_level == "corroborated"
    assert any("never called a rescue without measured convergence" in c for c in weak.caveats)


def test_ais_gap_feed_outage_is_not_a_vessel_gap():
    outage = assess_ais_gap(
        silence_s=1800, last_speed_kn=11.0, nearby_vessels_before=9,
        nearby_vessels_after=0, local_reporting_ratio=0.02,
    )
    vessel = assess_ais_gap(
        silence_s=5400, last_speed_kn=9.0, nearby_vessels_before=7,
        nearby_vessels_after=6, local_reporting_ratio=0.86,
    )
    assert "coverage outage" in outage.interpretation
    assert "vessel-specific" in vessel.interpretation
    assert "intentional dark activity" in outage.interpretation
    assert outage.confidence_components["coverage_quality"] < vessel.confidence_components["coverage_quality"]


def test_humanitarian_keeps_distinct_counts_and_the_credibility_caveat():
    a = assess_humanitarian(
        case_type="distress",
        people={"aboard": 45, "rescued": 12, "missing": 3, "approximate": True},
        vessel={"taking_water": True},
        needs=["rescue"],
        lifecycle="active",
    )
    assert "45 aboard" in a.observation and "3 missing" in a.observation
    assert any("Source credibility is not location credibility" in c for c in a.caveats)


def test_humanitarian_retrospective_does_not_open_a_case():
    a = assess_humanitarian(case_type="death_report", people={"dead": 27}, retrospective=True)
    assert "past event" in a.interpretation
    assert "no operational action" in a.recommended_action.lower()


def test_dispatch_and_version():
    a = assess("gap", {"silence_s": 3600, "last_speed_kn": 8.0})
    assert a is not None and a.rule_ids == ["ais_anomaly:gap"]
    assert a.classification_version == CLASSIFICATION_VERSION
    assert assess("nonsense", {}) is None
    assert assess("sudden_stop", {"bad_kwarg": 1}) is None
    assert "event_assessment" in a.as_metadata()
