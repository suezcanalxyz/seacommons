from datetime import datetime, timedelta, timezone

import pytest

from core.evidence.cross_modal import EvidenceReference
from core.intel.retrospective_validation import ClaimEvidence, compare_detectors, validate_claim


NOW = datetime(2026, 11, 26, tzinfo=timezone.utc)


def item(identifier, modality, *, lineage=None, relation="supports", delay=0, derived=False):
    evidence_class = {"ais": "ais_observation", "radio": "dsc_message",
                      "satellite": "satellite_observation", "documentary": "verification_claim"}[modality]
    return ClaimEvidence(
        EvidenceReference(identifier, evidence_class, lineage or modality, modality, NOW, .9, derived),
        relation, NOW + timedelta(hours=delay),
    )


def assess(*items, **kwargs):
    if "reviewed_by" in kwargs:
        kwargs.setdefault("reviewed_at", NOW)
    return validate_claim("episode-1", "event_occurrence", items, cutoff=NOW, **kwargs)


def test_unknown_and_late_evidence_do_not_count():
    report = assess(item("ais", "ais", derived=True), item("scene", "satellite", delay=1),
                    item("report", "documentary", lineage="unknown"))
    assert report.classification == "uncertain"
    assert report.later_evidence_ids == ("scene",)
    assert not report.suppress_public


def test_rebroadcast_is_one_lineage_even_across_modalities():
    report = assess(item("radio", "radio", lineage="coast_guard"),
                    item("report", "documentary", lineage="coast_guard"))
    assert report.classification == "uncertain"


def test_rebroadcast_does_not_supply_missing_modality_diversity():
    report = assess(item("radio", "radio", lineage="coast_guard"),
                    item("report", "documentary", lineage="coast_guard"),
                    item("other-radio", "radio", lineage="second-station"))
    assert report.classification == "uncertain"
    report = assess(item("ais", "ais", lineage="receiver"),
                    item("report", "documentary", lineage="receiver"))
    assert report.support_groups == ("ais",)
    assert report.classification == "uncertain"


def test_independent_support_is_probable_until_reviewed():
    evidence = (item("radio", "radio"), item("scene", "satellite"), item("report", "documentary"))
    assert assess(*evidence).classification == "probable"
    report = assess(*evidence, reviewed_by="researcher", review_reason="Matched same incident in primary records.")
    assert report.classification == "confirmed"
    assert report.confidence == "high"
    assert assess(*reversed(evidence), reviewed_by="researcher",
                  review_reason="Matched same incident in primary records.") == report


def test_false_positive_requires_positive_counterevidence_and_review():
    refutations = (item("radio", "radio", relation="contradicts"),
                   item("report", "documentary", relation="contradicts"))
    assert assess(*refutations).classification == "uncertain"
    refuted = assess(*refutations, reviewed_by="researcher", review_reason="Both records identify the cue as a drill.")
    assert refuted.classification == "false_positive"
    assert refuted.suppress_public
    conflicted = assess(*refutations, item("scene", "satellite"), reviewed_by="researcher",
                        review_reason="The scene still supports this claim.")
    assert conflicted.classification == "uncertain"
    assert not conflicted.suppress_public


def test_conflicting_duplicate_reference_rejected():
    with pytest.raises(ValueError, match="conflicting"):
        assess(item("one", "radio"), item("one", "radio", relation="contradicts"))


def test_detector_comparison_uses_paired_truth_and_reports_unresolved():
    truth = {"event": "confirmed", "drill": "false_positive", "gap": "uncertain"}
    baseline = {"event": True, "drill": True, "gap": True}
    candidate = {"event": True, "drill": False, "gap": None}
    result = compare_detectors(truth, baseline, candidate)
    assert result.baseline.precision == .5
    assert result.candidate.precision == 1
    assert result.candidate.recall == 1
    assert result.baseline.fp_ids == ["drill"]
    assert result.unresolved_truth == 1
    assert result.candidate_abstentions == 1
    with pytest.raises(ValueError, match="same"):
        compare_detectors(truth, baseline, {"event": True})


def test_abstaining_on_reviewed_event_counts_against_recall():
    result = compare_detectors({"event": "confirmed"}, {"event": True}, {"event": None})
    assert result.candidate.recall == 0
    assert result.candidate.precision is None
    assert result.candidate_abstentions == 1


def test_reviewed_negative_dossier_is_preserved_as_an_immutable_revision():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from core.db.models import AssessmentDB, HumanitarianIncidentDB, IntelEventDB, InvestigationHypothesisDB, MaritimeEpisodeDB
    from core.intel.retrospective_store import refuted_case_ids, store_dossier

    engine = create_engine("sqlite://")
    for model in (AssessmentDB, HumanitarianIncidentDB, IntelEventDB, InvestigationHypothesisDB, MaritimeEpisodeDB):
        model.__table__.create(engine)
    evidence = (item("radio", "radio", relation="contradicts"),
                item("report", "documentary", relation="contradicts"))
    original = assess(*evidence)
    reviewed = assess(*evidence, reviewed_by="researcher", review_reason="The cue was a drill.")
    with Session(engine) as db:
        with pytest.raises(ValueError, match="unknown canonical case"):
            store_dossier(db, reviewed)
        db.add(IntelEventDB(id="episode-1", timestamp_utc=NOW.isoformat(), type="ais_spike",
                            severity="medium", title="Synthetic drill", source="test"))
        db.flush()
        store_dossier(db, original)
        db.flush()
        negative = store_dossier(db, reviewed)
        db.flush()
        assert store_dossier(db, reviewed) is negative
        rows = db.scalars(select(AssessmentDB)).all()
        assert len(rows) == 2
        assert negative.review_state == "reviewed"
        assert negative.value["classification"] == "false_positive"
        assert negative.value["review_reason"] == "The cue was a drill."
        assert refuted_case_ids(db) == {"episode-1"}
        older_review = validate_claim(
            "episode-1", "event_occurrence", (), cutoff=NOW - timedelta(days=2),
            reviewed_by="researcher", review_reason="Older unresolved review.",
            reviewed_at=NOW - timedelta(days=1),
        )
        store_dossier(db, older_review)
        db.flush()
        assert refuted_case_ids(db) == {"episode-1"}


def test_private_cli_reports_backtest_metrics(tmp_path, monkeypatch, capsys):
    import json
    import sys

    from core.intel.retrospective_cli import main

    path = tmp_path / "bundle.json"
    path.write_text(json.dumps({
        "truth": {"case": "false_positive"},
        "baseline": {"case": True},
        "candidate": {"case": False},
    }), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["retrospective_cli", "backtest", str(path)])
    main()
    document = json.loads(capsys.readouterr().out)
    assert document["baseline"]["fp_ids"] == ["case"]
    assert document["baseline"]["precision"] == 0
    assert document["candidate"]["true_negatives"] == 1
