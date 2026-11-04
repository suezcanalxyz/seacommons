import pytest

from core.intel.maritime_attack_play_adapter import project_play_attack_review


def source(source_id, group, origin):
    return {
        "source_id": source_id, "independent_group": group,
        "primary_origin_id": origin,
        "source_url": f"https://example.org/{source_id}",
        "event_at": "2026-10-28T10:00:00Z",
        "published_at": "2026-10-28T11:00:00Z",
        "received_at": "2026-10-28T11:05:00Z",
        "imo": "9348625", "mmsi": "636019532",
        "position": (43.26, 28.81), "uncertainty_km": 10,
        "explicit_attack_claim": True,
    }


def test_play_projection_keeps_ais_context_only_and_blocks_publication():
    dossier = project_play_attack_review(
        case_id="contship-jet-20261028",
        source_records=[source("a", "authority", "official-report"),
                        source("b", "independent", "independent-investigation")],
        target_mmsi="636019532", event_at="2026-10-28T10:00:00Z", ais_records=[{"kind": "ais_gap", "mmsi": "636019532",
                      "observed_at": "2026-10-28T10:00:00Z"}],
    )
    assert dossier["review_status"] == "candidate_for_analyst_review"
    assert dossier["play_to_incident"] == "blocked_pending_analyst_review"
    assert dossier["automatic_publication"] is False
    assert dossier["attribution"] is None
    assert dossier["ais_context_signals"][0]["evidence_role"] == "context_only_not_attack_proof"
    assert dossier["projection_only"] is True


def test_shared_primary_origin_cannot_corrobate():
    dossier = project_play_attack_review(
        case_id="contship-jet-20261028",
        source_records=[source("a", "authority", "same-release"),
                        source("b", "press", "same-release")],
    )
    assert dossier["review_status"] == "insufficient_evidence"


@pytest.mark.parametrize("change", [
    {"explicit_attack_claim": False},
    {"primary_origin_id": ""},
    {"received_at": None},
])
def test_unvetted_or_incomplete_source_fails_closed(change):
    record = source("a", "authority", "official")
    record.update(change)
    if change.get("received_at", "ok") is None:
        dossier = project_play_attack_review(case_id="x", source_records=[record])
        assert dossier["review_status"] == "insufficient_evidence"
    else:
        with pytest.raises(ValueError):
            project_play_attack_review(case_id="x", source_records=[record])


def test_ais_alone_cannot_create_corrobated_incident():
    dossier = project_play_attack_review(case_id="x", source_records=[],
        target_mmsi="636019532", event_at="2026-10-28T10:00:00Z", ais_records=[{"kind": "sudden_stop", "mmsi": "636019532", "observed_at": "2026-10-28T10:00:00Z"}])
    assert dossier["review_status"] == "insufficient_evidence"


@pytest.mark.parametrize("signal", [
    {"kind": "ais_gap", "mmsi": "636019532", "observed_at": "not-a-date"},
    {"kind": "ais_gap", "mmsi": "636019532", "observed_at": "2026-10-28T10:00:00"},
    {"kind": "ais_gap", "mmsi": "636019532", "observed_at": "2026-10-28T10:00:00Z", "position": (float("nan"), 28.8)},
    {"kind": "ais_gap", "mmsi": "636019532", "position": (91.0, 28.8)},
    {"kind": "ais_gap", "mmsi": "636019532", "position": (43.2,)},
    {"kind": "ais_gap", "mmsi": "invalid", "observed_at": "2026-10-28T10:00:00Z"},
])
def test_malformed_ais_context_fails_closed(signal):
    with pytest.raises(ValueError):
        project_play_attack_review(case_id="contship-jet-20261028", source_records=[], target_mmsi="636019532", event_at="2026-10-28T10:00:00Z", ais_records=[signal])


def test_valid_ais_position_remains_context_not_proof():
    dossier = project_play_attack_review(
        case_id="contship-jet-20261028", source_records=[],
        target_mmsi="636019532", event_at="2026-10-28T10:00:00Z", ais_records=[{"kind": "ais_gap", "mmsi": "636019532",
                      "observed_at": "2026-10-28T10:00:00Z",
                      "position": [43.2, 28.8]}])
    assert dossier["review_status"] == "insufficient_evidence"
    assert dossier["ais_context_signals"][0]["evidence_role"] == "context_only_not_attack_proof"


@pytest.mark.parametrize("signal", [
    {"kind": "ais_gap", "mmsi": "123456789", "observed_at": "2026-10-28T10:00:00Z"},
    {"kind": "ais_gap", "mmsi": "636019532", "observed_at": "2026-11-02T10:00:00Z"},
    {"kind": "ais_gap", "mmsi": "636019532"},
])
def test_unrelated_or_untimed_ais_rejected(signal):
    with pytest.raises(ValueError):
        project_play_attack_review(case_id="contship-jet-20261028", source_records=[],
            target_mmsi="636019532", event_at="2026-10-28T10:00:00Z", ais_records=[signal])


def test_ais_context_requires_explicit_anchor():
    with pytest.raises(ValueError, match="ais_context_requires_target_identity_and_event_time"):
        project_play_attack_review(case_id="x", source_records=[],
            ais_records=[{"kind": "ais_gap", "mmsi": "636019532", "observed_at": "2026-10-28T10:00:00Z"}])
