# SPDX-License-Identifier: AGPL-3.0-or-later
"""Location provenance regression: documentary estimates must not masquerade as AIS."""
from dataclasses import replace
from core.intel.maritime_attack_gate import AttackEvidence, evaluate_attack_candidate

BASE = dict(
    source_id="official-release", independent_group="authority",
    primary_origin_id="authority-original", source_url="https://example.org/official",
    event_at="2026-10-28T10:00:00Z",
    published_at="2026-10-28T11:00:00Z",
    received_at="2026-10-28T12:00:00Z",
    imo="9348625", mmsi="636019532", position=(43.0, 29.0),
    explicit_attack_claim=True,
)

def second():
    return AttackEvidence(**{**BASE, "source_id": "owner", "independent_group": "owner",
        "primary_origin_id": "owner-original", "source_url": "https://example.org/owner"})

def test_documentary_position_is_retained_not_relabelled_ais():
    first = AttackEvidence(**{**BASE, "position_provenance": "coastal_reference"})
    other = replace(second(), position_provenance="documentary_estimate")
    result = evaluate_attack_candidate([first, other])
    assert result["status"] == "candidate_for_analyst_review"
    assert [s["position_provenance"] for s in result["sources"]] == [
        "coastal_reference", "documentary_estimate"]
    assert result["automatic_publication"] is False
    assert result["attribution"] is None

def test_unknown_position_origin_fails_closed():
    first = AttackEvidence(**{**BASE, "position_provenance": "satellite_confirmed"})
    result = evaluate_attack_candidate([first, second()])
    assert result["status"] == "insufficient_evidence"
    assert "invalid_position_provenance" in result["reasons"]
    assert result["automatic_publication"] is False

def test_origin_without_coordinates_fails_closed():
    first = AttackEvidence(**{**BASE, "position": None, "position_provenance": "ais_observed"})
    result = evaluate_attack_candidate([first, second()])
    assert result["status"] == "insufficient_evidence"
    assert "invalid_position_provenance" in result["reasons"]

def test_cross_sea_positions_remain_distinct_even_with_uncertainty():
    first = AttackEvidence(**{**BASE, "position_provenance": "documentary_estimate", "uncertainty_km": 20})
    other = replace(second(), position=(41.0, 40.0), position_provenance="ais_observed")
    result = evaluate_attack_candidate([first, other])
    assert result["status"] == "insufficient_evidence"
    assert "spatial_mismatch" in result["reasons"]


def test_empty_evidence_explicitly_disables_publication_and_attribution():
    result = evaluate_attack_candidate([])
    assert result["status"] == "insufficient_evidence"
    assert result["reasons"] == ["no_evidence"]
    assert result["sources"] == []
    assert result["automatic_publication"] is False
    assert result["attribution"] is None

def test_rejected_evidence_retains_source_level_audit_without_promotion():
    invalid = AttackEvidence(**{**BASE, "source_id": "bad-coordinate",
        "position": (95.0, 29.0), "position_provenance": "ais_observed"})
    result = evaluate_attack_candidate([invalid, second()])
    assert result["status"] == "insufficient_evidence"
    assert {"source_id": "bad-coordinate", "reason": "invalid_position"} in result["rejected_evidence"]
    assert all(source["id"] != "bad-coordinate" for source in result["sources"])
    assert result["automatic_publication"] is False
    assert result["attribution"] is None
