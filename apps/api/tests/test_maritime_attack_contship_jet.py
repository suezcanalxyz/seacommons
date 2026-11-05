"""CONTSHIP JET regression: synthetic evidence only, not historical AIS observations."""
from dataclasses import replace

from core.intel.maritime_attack_gate import AttackEvidence, evaluate_attack_candidate


def _evidence():
    authority = AttackEvidence(
        source_id="bulgaria-statement",
        independent_group="bulgarian-authority",
        primary_origin_id="bulgarian-ministry-release-20261028",
        source_url="https://example.org/bulgaria/release",
        event_at="2026-10-28T10:00:00Z",
        published_at="2026-10-28T12:00:00Z",
        received_at="2026-10-28T12:10:00Z",
        imo="9348625",
        mmsi="636019532",
        explicit_attack_claim=True,
        event_uncertainty_minutes=60,
    )
    owner = replace(
        authority,
        source_id="shipowner-statement",
        independent_group="shipowner",
        primary_origin_id="shipowner-direct-statement-20261028",
        source_url="https://example.net/shipowner/statement",
        event_at="2026-10-28T10:45:00Z",
        published_at="2026-10-28T13:00:00Z",
        received_at="2026-10-28T13:10:00Z",
    )
    return authority, owner


def test_distinct_origins_compatible_times_review_only():
    result = evaluate_attack_candidate(list(_evidence()))
    assert result["status"] == "candidate_for_analyst_review"
    assert result["automatic_publication"] is False
    assert result["attribution"] is None


def test_two_publishers_same_upstream_release_are_not_independent():
    authority, owner = _evidence()
    syndicated = replace(owner, primary_origin_id=authority.primary_origin_id)
    result = evaluate_attack_candidate([authority, syndicated])
    assert result["status"] == "insufficient_evidence"
    assert "duplicate_source" in result["reasons"]


def test_ais_gap_cannot_supply_second_attack_confirmation():
    authority, owner = _evidence()
    gap = replace(owner, explicit_attack_claim=False, signal_only=True)
    result = evaluate_attack_candidate([authority, gap])
    assert result["status"] == "insufficient_evidence"
    assert "fewer_than_two_independent_attack_claims" in result["reasons"]


def test_conflicting_mmsi_fails_closed_despite_matching_imo():
    authority, owner = _evidence()
    conflict = replace(owner, mmsi="636019533")
    result = evaluate_attack_candidate([authority, conflict])
    assert result["status"] == "insufficient_evidence"
    assert "mmsi_conflict" in result["reasons"]


def test_time_mismatch_not_hidden_by_uncertainty():
    authority, owner = _evidence()
    late = replace(owner, event_at="2026-10-30T10:00:00Z", published_at="2026-10-30T12:00:00Z", received_at="2026-10-30T13:00:00Z")
    result = evaluate_attack_candidate([authority, late])
    assert result["status"] == "insufficient_evidence"
    assert "time_mismatch" in result["reasons"]
