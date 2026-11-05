"""Regression tests for bounded uncertainty in maritime incident timestamps."""
from dataclasses import replace

from core.intel.maritime_attack_gate import AttackEvidence, evaluate_attack_candidate


def _pair():
    base = AttackEvidence(
        source_id="bulgarian-authority",
        independent_group="authority",
        primary_origin_id="bulgarian-release",
        source_url="https://example.org/authority",
        event_at="2026-10-28T10:00:00Z",
        published_at="2026-10-29T12:00:00Z",
        received_at="2026-10-29T13:00:00Z",
        imo="9348625",
        mmsi="636019532",
        explicit_attack_claim=True,
    )
    second = replace(
        base,
        source_id="shipowner",
        independent_group="shipowner",
        primary_origin_id="shipowner-statement",
        source_url="https://example.net/shipowner",
        event_at="2026-10-28T23:00:00Z",
    )
    return base, second


def test_bounded_uncertainty_can_bridge_thirteen_hour_offset():
    a, b = _pair()
    assert "time_mismatch" in evaluate_attack_candidate([a, b])["reasons"]
    result = evaluate_attack_candidate([
        replace(a, event_uncertainty_minutes=60),
        replace(b, event_uncertainty_minutes=60),
    ])
    assert result["status"] == "candidate_for_analyst_review"
    assert result["automatic_publication"] is False
    assert result["attribution"] is None


def test_uncertainty_does_not_bridge_unrelated_events():
    a, b = _pair()
    b = replace(b, event_at="2026-10-30T23:00:00Z")
    result = evaluate_attack_candidate([
        replace(a, event_uncertainty_minutes=180),
        replace(b, event_uncertainty_minutes=180),
    ])
    assert result["status"] == "insufficient_evidence"
    assert "time_mismatch" in result["reasons"]


def test_invalid_uncertainty_fails_closed():
    a, b = _pair()
    for invalid in (True, -1, 181, float("nan"), "60", None):
        result = evaluate_attack_candidate([
            replace(a, event_uncertainty_minutes=invalid), b
        ])
        assert result["status"] == "insufficient_evidence"
        assert "invalid_time_uncertainty" in result["reasons"]
        assert result["automatic_publication"] is False
