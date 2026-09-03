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

from core.intel.alert_recognition_scorer import render_report, run_all, score_ais_status, score_humanitarian


def test_scorer_runs_against_all_four_fixture_files():
    reports = run_all()
    names = {r.filename for r in reports}
    assert names == {
        "humanitarian.jsonl", "ais_status.jsonl", "ais_behaviour.jsonl", "ais_integrity.jsonl",
    }
    scored = {r.filename: r.scored for r in reports}
    assert scored["humanitarian.jsonl"] is True
    assert scored["ais_status.jsonl"] is True
    assert scored["ais_behaviour.jsonl"] is False
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
    assert "NOT YET SCORED" in text  # ais_behaviour / ais_integrity
