from core.intel.maritime_attack_gate import AttackEvidence
from core.intel.maritime_attack_review import (
    ATTACK_CATEGORY, HUMANITARIAN_CATEGORY, build_attack_review_dossier,
)


def evidence(source, group):
    return AttackEvidence(
        source_id=source, independent_group=group,
        source_url=f"https://example.org/{source}",
        event_at="2026-10-28T10:00:00Z",
        published_at="2026-10-28T11:00:00Z",
        received_at="2026-10-28T11:10:00Z",
        imo="9348625", mmsi="636019532", position=(43.26, 28.81),
        explicit_attack_claim=True,
    )


def test_review_dossier_never_auto_publishes():
    dossier = build_attack_review_dossier([evidence("official", "government"), evidence("press", "press")])
    assert dossier["review_status"] == "candidate_for_analyst_review"
    assert dossier["play_to_incident"] == "blocked_pending_analyst_review"
    assert dossier["automatic_publication"] is False
    assert dossier["attribution"] is None
    assert dossier["audit"]["writes_performed"] is False


def test_ais_only_never_corrobates_attack():
    dossier = build_attack_review_dossier([], ais_observations=[
        {"kind": "ais_gap", "mmsi": "636019532", "observed_at": "2026-10-28T10:00:00Z"}
    ])
    assert dossier["review_status"] == "insufficient_evidence"
    assert dossier["ais_context_signals"][0]["evidence_role"] == "context_only_not_attack_proof"


def test_dossier_hash_is_stable_and_order_independent():
    a, b = evidence("official", "government"), evidence("press", "press")
    first = build_attack_review_dossier([a, b])
    second = build_attack_review_dossier([b, a])
    assert first["audit"]["input_sha256"] == second["audit"]["input_sha256"]
    assert first["case_id"] == second["case_id"]


def test_attack_visual_category_distinct_from_humanitarian():
    dossier = build_attack_review_dossier([])
    assert dossier["category"] == ATTACK_CATEGORY
    assert dossier["category"] != HUMANITARIAN_CATEGORY
    assert dossier["display_color"].startswith("#")


def test_dossier_preserves_vessel_identity_and_geospatial_uncertainty():
    dossier = build_attack_review_dossier([evidence("official", "government"), evidence("press", "press")])
    source = next(row for row in dossier["source_provenance"] if row["id"] == "official")
    assert source["imo"] == "9348625"
    assert source["mmsi"] == "636019532"
    assert source["position"] == [43.26, 28.81]
    assert source["uncertainty_km"] == 0
    assert source["independent_group"] == "government"
    assert source["explicit_attack_claim"] is True
    assert source["event_at"] == "2026-10-28T10:00:00Z"
    assert source["published_at"] == "2026-10-28T11:00:00Z"
    assert source["received_at"] == "2026-10-28T11:10:00Z"


def test_uncertainty_change_changes_dossier_audit_hash():
    from dataclasses import replace
    a, b = evidence("official", "government"), evidence("press", "press")
    original = build_attack_review_dossier([a, b])
    changed = build_attack_review_dossier([replace(a, uncertainty_km=15), b])
    assert original["audit"]["input_sha256"] != changed["audit"]["input_sha256"]
