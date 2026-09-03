# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/prompt.md Phase 3 -- evaluation corpus scorer.

Locks in the current baseline numbers as a regression guard: this session's
priority order requires establishing precision/recall/F1 *before* any
detector threshold changes, and the whole point is defeated if a future
change to is_distress() or classify_service() silently shifts these numbers
without anyone noticing. If a fix intentionally changes them, update this
test in the same PR as the fix -- not silently.
"""
from __future__ import annotations

from core.intel.alert_recognition_scorer import (
    render_report,
    run_all,
    score_ais_behaviour,
    score_ais_status,
    score_humanitarian,
    score_humanitarian_recognition,
)


def test_scorer_runs_against_all_five_fixture_reports():
    reports = run_all()
    names = {r.filename for r in reports}
    assert names == {
        "humanitarian.jsonl", "humanitarian.jsonl (recognition v2)",
        "ais_status.jsonl", "ais_behaviour.jsonl", "ais_integrity.jsonl",
    }
    scored = {r.filename: r.scored for r in reports}
    assert scored["humanitarian.jsonl"] is True
    assert scored["humanitarian.jsonl (recognition v2)"] is True
    assert scored["ais_status.jsonl"] is True
    assert scored["ais_behaviour.jsonl"] is True
    assert scored["ais_integrity.jsonl"] is False


def test_humanitarian_baseline_is_locked():
    """is_distress() baseline after the false-positive fix: 0 false
    positives, 0 false negatives, on the exact fixtures that used to false-
    positive (docs/ALERT_RECOGNITION_BASELINE.md)."""
    report = score_humanitarian()
    cls = report.classes["is_distress"]
    assert cls.false_negatives == 0
    assert cls.fp_ids == []
    assert cls.precision == 1.0
    assert cls.recall == 1.0


def test_humanitarian_recognition_baseline_is_locked():
    """docs/fixes.md M2.1: core.intel.humanitarian_recognition.assess()
    scored against the same corpus. hum-004 (French distress phrasing) is
    the one KNOWN, documented gap -- see its fixture note -- so it is the
    sole expected false negative on case_type/lifecycle/publication.
    people_counts has zero false negatives: every expected_counts value in
    the corpus is one this module's extractor actually produces."""
    report = score_humanitarian_recognition()
    assert report.classes["case_type"].fn_ids == ["hum-004"]
    assert report.classes["lifecycle"].fn_ids == ["hum-004"]
    assert report.classes["publication_recommendation"].fn_ids == ["hum-004"]
    assert report.classes["people_counts"].fn_ids == []
    for cls in report.classes.values():
        assert cls.false_positives == 0, f"{cls.label}: {cls.fp_ids}"


def test_ais_behaviour_baseline_is_clean():
    """docs/fixes.md M4.1: core.intel.ais_behaviour_replay.classify() was
    built to match this exact fixture set, so it scores perfectly -- a
    regression here means a later change broke a case this corpus already
    covers. unscored_count is 0: every current fixture's kind (sudden_stop/
    rescue_cluster/ngo_search_pattern) is implemented."""
    report = score_ais_behaviour()
    for cls in report.classes.values():
        assert cls.false_positives == 0, f"{cls.label}: {cls.fp_ids}"
        assert cls.false_negatives == 0, f"{cls.label}: {cls.fn_ids}"
    assert report.unscored_count == 0


def test_ais_status_baseline_is_clean():
    """classify_service() (this session's own PR #61) was built against
    these exact fixtures, so it should score perfectly -- a regression here
    means a later change broke a case this corpus already covers."""
    report = score_ais_status()
    for label, cls in report.classes.items():
        assert cls.false_positives == 0, f"{label}: {cls.fp_ids}"
        assert cls.false_negatives == 0, f"{label}: {cls.fn_ids}"


def test_render_report_produces_markdown_with_no_crash():
    text = render_report(run_all())
    assert "# Alert Recognition Baseline" in text
    assert "humanitarian.jsonl" in text
    assert "NOT YET SCORED" in text  # ais_integrity
