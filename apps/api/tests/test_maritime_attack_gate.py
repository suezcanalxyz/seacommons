from core.intel.maritime_attack_gate import AttackEvidence, evaluate_attack_candidate

BASE = dict(event_at="2026-10-28T10:00:00Z", published_at="2026-10-28T11:00:00Z",
            received_at="2026-10-28T11:05:00Z", imo="9348625", mmsi="636019532",
            position=(41.0, 30.0), explicit_attack_claim=True)

def item(name, group, **overrides):
    return AttackEvidence(**(BASE | dict(source_id=name, independent_group=group,
                                         source_url=f"https://example.org/{name}") | overrides))

def test_independent_sources_only_promote_to_review():
    result = evaluate_attack_candidate([item("a","authority"), item("b","press")])
    assert result["status"] == "candidate_for_analyst_review"
    assert result["automatic_publication"] is False
    assert result["attribution"] is None

def test_same_syndicated_group_is_not_double_corroboration():
    assert evaluate_attack_candidate([item("a","wire"),item("b","wire")])["status"] == "insufficient_evidence"

def test_ais_gap_not_attack_proof():
    assert evaluate_attack_candidate([item("gap","ais",explicit_attack_claim=False,signal_only=True),item("a","press")])["status"] == "insufficient_evidence"

def test_conflicting_imo_fails_closed():
    result = evaluate_attack_candidate([item("a","authority"),item("b","press",imo="9999999")])
    assert result["status"] == "insufficient_evidence"
    assert "imo_conflict" in result["reasons"]

def test_spatial_mismatch_fails_closed():
    assert evaluate_attack_candidate([item("a","authority"),item("b","press",position=(10,10))])["status"] == "insufficient_evidence"

def test_time_mismatch_fails_closed():
    assert evaluate_attack_candidate([item("a","authority"),item("b","press",event_at="2026-10-30T10:00:00Z",published_at="2026-10-30T11:00:00Z",received_at="2026-10-30T11:05:00Z")])["status"] == "insufficient_evidence"

def test_missing_provenance_fails_closed():
    assert evaluate_attack_candidate([item("a","authority"),item("b","press",source_url="")])["status"] == "insufficient_evidence"

def test_timezone_required():
    assert evaluate_attack_candidate([item("a","authority"),item("b","press",event_at="2026-10-28T10:00:00")])["status"] == "insufficient_evidence"
