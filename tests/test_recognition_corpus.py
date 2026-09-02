# SPDX-License-Identifier: AGPL-3.0-or-later
"""The alert-recognition evaluation corpus + scorer (docs/prompt.md PHASE 3)."""
from __future__ import annotations

import pytest

from tests.fixtures.alert_recognition import (
    CORPUS_NAMES,
    CorpusRow,
    load_all,
    load_corpus,
    run,
    score,
)

_LIFECYCLES = {"active", "ongoing", "needs_review", "resolved", "concluded"}


@pytest.mark.parametrize("name", CORPUS_NAMES)
def test_every_corpus_file_loads_and_is_well_formed(name):
    rows = load_corpus(name)
    assert rows, name
    ids = [r.id for r in rows]
    assert len(ids) == len(set(ids)), f"duplicate ids in {name}"
    for row in rows:
        assert row.lifecycle in _LIFECYCLES, (row.id, row.lifecycle)
        lo, hi = row.confidence_range
        assert 0.0 <= lo <= hi <= 1.0
        assert row.notes


def test_corpus_has_negatives_in_every_file():
    for name in CORPUS_NAMES:
        rows = load_corpus(name)
        assert any(
            r.expects_no_alert or r.is_contrastive_negative for r in rows
        ), f"{name} has no negative case"


def test_no_alert_rows_expect_low_confidence_and_non_public():
    checked = 0
    for row in load_all():
        if row.expects_no_alert:
            checked += 1
            assert row.confidence_range[1] <= 0.4, row.id
            assert row.publication in {"internal", "private"}, row.id
    assert checked >= 4


def test_advocacy_is_never_published():
    for row in load_all():
        if row.classification == "advocacy":
            assert row.publication == "internal", row.id
            assert row.confidence_range[1] <= 0.3, row.id


def test_scorer_computes_precision_recall_f1():
    rows = [
        CorpusRow("a", "t", {}, "distress", "active", {}, "published", (0.5, 1.0), "n"),
        CorpusRow("b", "t", {}, "distress", "active", {}, "published", (0.5, 1.0), "n"),
        CorpusRow("c", "t", {}, "missing_persons", "active", {}, "published", (0.5, 1.0), "n"),
        CorpusRow("d", "t", {}, "none", "concluded", {}, "private", (0.0, 0.3), "HARD NEGATIVE"),
    ]
    predictions = {
        "a": {"classification": "distress"},          # tp distress
        "b": {"classification": "missing_persons"},    # fp missing, fn distress
        "c": {"classification": "missing_persons"},    # tp missing
        "d": {"classification": "distress"},           # fp distress, fn none
    }
    report = score(rows, predictions)
    distress = report.per_class["distress"]
    assert (distress.tp, distress.fp, distress.fn) == (1, 1, 1)
    assert distress.precision == 0.5 and distress.recall == 0.5
    missing = report.per_class["missing_persons"]
    assert (missing.tp, missing.fp, missing.fn) == (1, 1, 0)


def test_scorer_tracks_publication_and_confidence_when_predicted():
    rows = [
        CorpusRow("a", "t", {}, "distress", "active", {}, "published", (0.6, 0.9), "n"),
    ]
    good = score(rows, {"a": {"classification": "distress", "publication": "published", "confidence": 0.7, "lifecycle": "active"}})
    assert good.publication_accuracy == 1.0
    assert good.confidence_in_range == 1.0
    assert good.lifecycle_accuracy == 1.0
    bad = score(rows, {"a": {"classification": "distress", "publication": "internal", "confidence": 0.2}})
    assert bad.publication_accuracy == 0.0
    assert bad.confidence_in_range == 0.0


def test_run_helper_scores_a_classifier_over_the_whole_corpus():
    # a trivial baseline: always predict the row's own class -> perfect score,
    # proving the harness plumbs end to end (real classifiers arrive in later PRs)
    report = run(lambda row: {"classification": row.classification})
    assert report.n == len(load_all())
    assert report.macro_f1() == 1.0
    assert not report.mismatches


def test_run_helper_surfaces_mismatches_for_a_bad_classifier():
    report = run(lambda row: {"classification": "distress"})
    assert report.mismatches
    assert report.macro_f1() < 1.0
