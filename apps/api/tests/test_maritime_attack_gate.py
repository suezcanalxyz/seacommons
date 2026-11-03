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

def test_invalid_chronology_cannot_count_as_independent_claim():
    result = evaluate_attack_candidate([
        item("a", "authority"),
        item("b", "press", published_at="2026-10-28T09:00:00Z"),
    ])
    assert result["status"] == "insufficient_evidence"
    assert "chronology_requires_review" in result["reasons"]


def test_duplicate_source_does_not_count_twice():
    first = item("a", "authority")
    duplicate = item("a", "press")
    result = evaluate_attack_candidate([first, duplicate])
    assert result["status"] == "insufficient_evidence"
    assert "duplicate_source" in result["reasons"]


def test_ais_gap_and_unrelated_press_do_not_corroborate():
    result = evaluate_attack_candidate([
        item("gap", "ais", explicit_attack_claim=False, signal_only=True),
        item("press", "media", position=(10, 10)),
    ])
    assert result["status"] == "insufficient_evidence"

def test_same_location_different_vessels_cannot_corroborate():
    result = evaluate_attack_candidate([
        item("a", "authority"),
        item("b", "press", imo="9999999", mmsi="999999999"),
    ])
    assert result["status"] == "insufficient_evidence"


def test_missing_common_identity_fails_closed():
    result = evaluate_attack_candidate([
        item("a", "authority", imo=None, mmsi=None),
        item("b", "press", imo=None, mmsi=None),
    ])
    assert result["status"] == "insufficient_evidence"
    assert "unresolved_vessel_identity" in result["reasons"]


def test_shared_mmsi_without_imo_allows_review():
    result = evaluate_attack_candidate([
        item("a", "authority", imo=None),
        item("b", "press", imo=None),
    ])
    assert result["status"] == "candidate_for_analyst_review"


def test_negative_uncertainty_rejected():
    result = evaluate_attack_candidate([
        item("a", "authority"),
        item("b", "press", uncertainty_km=-100),
    ])
    assert result["status"] == "insufficient_evidence"

def test_conflicting_third_claim_cannot_be_ignored():
    evidence = [item("a", "authority"), item("b", "press"),
                item("c", "other", imo="9999999")]
    assert evaluate_attack_candidate(evidence)["status"] == "insufficient_evidence"
    assert evaluate_attack_candidate(list(reversed(evidence)))["status"] == "insufficient_evidence"


def test_duplicate_article_url_with_different_source_id_is_one_source():
    evidence = [item("a", "authority"),
                item("b", "press", source_url="https://example.org/a?utm_source=copy")]
    result = evaluate_attack_candidate(evidence)
    assert result["status"] == "insufficient_evidence"
    assert "duplicate_source" in result["reasons"]

def test_same_source_id_with_different_urls_is_not_independent():
    result = evaluate_attack_candidate([
        item("authority-1", "authority"),
        item("authority-1", "press", source_url="https://different.example.org/story"),
    ])
    assert result["status"] == "insufficient_evidence"
    assert "duplicate_source" in result["reasons"]


def test_nan_coordinate_cannot_bypass_spatial_gate():
    result = evaluate_attack_candidate([
        item("a", "authority"),
        item("b", "press", position=(float("nan"), 30.0)),
    ])
    assert result["status"] == "insufficient_evidence"
    assert "invalid_position" in result["reasons"]


def test_infinite_uncertainty_cannot_bypass_spatial_gate():
    result = evaluate_attack_candidate([
        item("a", "authority"),
        item("b", "press", uncertainty_km=float("inf")),
    ])
    assert result["status"] == "insufficient_evidence"
    assert "invalid_position" in result["reasons"]

def test_invalid_imo_checksum_fails_closed():
    result = evaluate_attack_candidate([item("a", "official"), item("b", "press", imo="9348626")])
    assert result["status"] == "insufficient_evidence"
    assert "invalid_vessel_identifier" in result["reasons"]


def test_invalid_mmsi_length_fails_closed():
    result = evaluate_attack_candidate([item("a", "official"), item("b", "press", mmsi="63601953")])
    assert result["status"] == "insufficient_evidence"
    assert "invalid_vessel_identifier" in result["reasons"]


def test_nan_matching_threshold_cannot_bypass_spatial_check():
    result = evaluate_attack_candidate([item("a", "official"), item("b", "press")], max_km=float("nan"))
    assert result["status"] == "insufficient_evidence"
    assert "invalid_matching_threshold" in result["reasons"]


def test_valid_contship_jet_identifiers_still_match():
    result = evaluate_attack_candidate([item("a", "official"), item("b", "press")])
    assert result["status"] == "candidate_for_analyst_review"
