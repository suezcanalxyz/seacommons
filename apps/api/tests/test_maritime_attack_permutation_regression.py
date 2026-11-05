"""Fail-closed regression for source-order invariance and contradictory vessel reports.

All records are synthetic fixtures; no assertion establishes a real-world attack.
"""
from itertools import permutations

from core.intel.maritime_attack_gate import AttackEvidence, evaluate_attack_candidate


def _claim(source_id, group, origin, *, imo=None, mmsi=None, position=None):
    return AttackEvidence(
        source_id=source_id,
        independent_group=group,
        primary_origin_id=origin,
        source_url=f"https://example.org/{source_id}",
        event_at="2026-10-28T10:00:00Z",
        published_at="2026-10-28T11:00:00Z",
        received_at="2026-10-28T12:00:00Z",
        imo=imo,
        mmsi=mmsi,
        position=position,
        explicit_attack_claim=True,
    )


def test_conflicting_vessel_claims_fail_closed_in_every_order():
    claims = [
        _claim("unidentified", "wire", "wire-original"),
        _claim("vessel-a", "wire", "wire-followup", imo="9348625"),
        _claim("vessel-b", "authority", "authority-original", imo="9348637"),
    ]
    for ordered in permutations(claims):
        result = evaluate_attack_candidate(list(ordered))
        assert result["status"] == "insufficient_evidence"
        assert "imo_conflict" in result["reasons"]
        assert result["automatic_publication"] is False
        assert result["attribution"] is None


def test_spatial_conflict_fails_closed_in_every_order():
    claims = [
        _claim("no-position", "wire", "wire-original", imo="9348625"),
        _claim("black-sea", "wire", "wire-followup", imo="9348625", position=(43.0, 30.0)),
        _claim("red-sea", "authority", "authority-original", imo="9348625", position=(15.0, 42.0)),
    ]
    for ordered in permutations(claims):
        result = evaluate_attack_candidate(list(ordered))
        assert result["status"] == "insufficient_evidence"
        assert "spatial_mismatch" in result["reasons"]
        assert result["automatic_publication"] is False


def test_two_independent_compatible_claims_still_require_analyst_review():
    claims = [
        _claim("authority", "authority", "ministry-original", imo="9348625", mmsi="636019532"),
        _claim("operator", "operator", "operator-original", imo="9348625", mmsi="636019532"),
    ]
    result = evaluate_attack_candidate(claims)
    assert result["status"] == "candidate_for_analyst_review"
    assert result["automatic_publication"] is False
    assert result["attribution"] is None


def test_duplicate_origin_conflict_cannot_be_hidden_by_deduplication():
    """Contradictory revisions of one origin cannot be discarded by input order."""
    claims = [
        _claim("ministry-a", "authority", "ministry-release", imo="9348625"),
        _claim("ministry-correction", "authority", "ministry-release", imo="9348637"),
        _claim("operator", "operator", "operator-release", imo="9348625"),
    ]
    for ordered in permutations(claims):
        result = evaluate_attack_candidate(list(ordered))
        assert result["status"] == "insufficient_evidence"
        assert "imo_conflict" in result["reasons"]
        assert "duplicate_source" in result["reasons"]
        assert result["automatic_publication"] is False
        assert result["attribution"] is None
