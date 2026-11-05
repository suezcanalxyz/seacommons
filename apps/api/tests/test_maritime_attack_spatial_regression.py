"""Fail-closed spatial and source-origin regression scenarios (synthetic data)."""
from dataclasses import replace

from core.intel.maritime_attack_gate import AttackEvidence, evaluate_attack_candidate


def _pair():
    a = AttackEvidence(
        source_id="official-release", independent_group="authority",
        primary_origin_id="release-1", source_url="https://example.org/a",
        event_at="2026-10-28T10:00:00Z",
        published_at="2026-10-28T11:00:00Z",
        received_at="2026-10-28T11:10:00Z",
        imo="9348625", mmsi="636019532", position=(43.0, 28.0),
        explicit_attack_claim=True,
    )
    b = replace(
        a, source_id="owner-direct", independent_group="owner",
        primary_origin_id="owner-1", source_url="https://example.net/b",
        position=(43.01, 28.01),
    )
    return a, b


def test_nearby_positions_allow_review_not_publication():
    result = evaluate_attack_candidate(list(_pair()))
    assert result["status"] == "candidate_for_analyst_review"
    assert result["automatic_publication"] is False
    assert result["attribution"] is None


def test_different_seas_are_not_bridged_by_matching_identity():
    a, b = _pair()
    b = replace(b, position=(25.0, 55.0))
    result = evaluate_attack_candidate([a, b])
    assert result["status"] == "insufficient_evidence"
    assert "spatial_mismatch" in result["reasons"]


def test_large_geographic_uncertainty_fails_closed():
    a, b = _pair()
    result = evaluate_attack_candidate([a, replace(b, uncertainty_km=1000)])
    assert result["status"] == "insufficient_evidence"
    assert "invalid_position" in result["reasons"]


def test_ais_gap_is_signal_only_even_when_claim_flag_is_true():
    a, b = _pair()
    result = evaluate_attack_candidate([a, replace(b, signal_only=True)])
    assert result["status"] == "insufficient_evidence"
    assert "fewer_than_two_independent_attack_claims" in result["reasons"]


def test_two_domains_reprinting_one_origin_are_not_independent():
    a, b = _pair()
    result = evaluate_attack_candidate([a, replace(b, primary_origin_id=a.primary_origin_id)])
    assert result["status"] == "insufficient_evidence"
    assert "duplicate_source" in result["reasons"]
