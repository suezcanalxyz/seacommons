"""Regression: downstream PLAY consumers must always receive a complete audit envelope."""
from core.intel.maritime_attack_gate import AttackEvidence, evaluate_attack_candidate


def _assert_fail_closed_contract(result):
    assert result["status"] == "insufficient_evidence"
    assert result["automatic_publication"] is False
    assert result["attribution"] is None
    assert isinstance(result["sources"], list)
    assert isinstance(result["rejected_evidence"], list)
    assert isinstance(result["independent_groups"], list)
    assert isinstance(result["reasons"], list)


def test_empty_input_keeps_audit_contract():
    result = evaluate_attack_candidate([])
    _assert_fail_closed_contract(result)
    assert result["reasons"] == ["no_evidence"]
    assert result["rejected_evidence"] == []
    assert result["independent_groups"] == []


def test_invalid_threshold_keeps_audit_contract():
    result = evaluate_attack_candidate([], max_hours=float("nan"))
    # Empty input takes precedence, but the envelope remains stable.
    _assert_fail_closed_contract(result)
    result = evaluate_attack_candidate([
        AttackEvidence(
            source_id="ais-only", independent_group="ais",
            source_url="https://example.org/ais",
            event_at="2026-10-28T10:00:00Z",
            published_at="2026-10-28T11:00:00Z",
            received_at="2026-10-28T12:00:00Z",
            imo="9348625", mmsi="636019532",
            signal_only=True,
        )
    ], max_km=float("nan"))
    _assert_fail_closed_contract(result)
    assert "invalid_matching_threshold" in result["reasons"]
    assert result["rejected_evidence"] == []
    assert result["independent_groups"] == []
