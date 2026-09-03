# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evaluation corpus scorer (docs/prompt.md Phase 3).

Scores ``tests/fixtures/alert_recognition/*.jsonl`` against whichever
deterministic classifiers already exist in this codebase, and reports
precision/recall/F1 per class plus explicit false-positive/false-negative
lists -- required before any detector threshold is touched (this session's
priority order; docs/prompt.md: "Do not claim an improvement unless the
evaluation corpus demonstrates it").

v0 scope: all four fixture files are scored today, against functions
that already exist as pure, callable classifiers:

  humanitarian.jsonl  -> core.intel.geoextract.is_distress(text)
                       -> core.intel.humanitarian_recognition.assess(text)
                          (docs/fixes.md M2.1 -- case_type/lifecycle/
                          people-count/publication accuracy, a second,
                          independent report over the same corpus)
  ais_status.jsonl    -> core.intel.service_taxonomy.classify_service(metadata)
  ais_behaviour.jsonl -> core.intel.ais_behaviour_replay.classify(input)
                          (docs/fixes.md M4.1 -- sudden_stop/rescue_cluster/
                          ngo_search_pattern only; vessel_loiter has no
                          fixture/classifier yet and is reported as its
                          own unscored_count within an otherwise-scored
                          report, not silently dropped)
  ais_integrity.jsonl -> core.intel.ais_integrity_replay.classify(input)
                          (docs/fixes.md M4.1/M4.3 -- gap/impossible_speed/
                          dark_zone_entry; the gap classifier reasons from
                          a neighbour-reporting ratio, never vessel type,
                          satisfying M4.3's "vessel class becomes a
                          contextual feature only" for this classifier by
                          construction -- it has no vessel_type parameter
                          to exclude on. NOT wired into the live
                          core.mda.watch.scan_gaps()/scan_spoofing()
                          detectors yet; that remains a separate,
                          larger, carefully-reviewed PR)

Run: ``python -m core.intel.alert_recognition_scorer``
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

_FIXTURES_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "alert_recognition"


@dataclass
class ClassResult:
    label: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0
    fp_ids: list[str] = field(default_factory=list)
    fn_ids: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float | None:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else None

    @property
    def recall(self) -> float | None:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)


@dataclass
class FileReport:
    filename: str
    scored: bool
    classes: dict[str, ClassResult] = field(default_factory=dict)
    unscored_count: int = 0
    total: int = 0


def _load_jsonl(name: str) -> list[dict[str, Any]]:
    path = _FIXTURES_DIR / name
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _record(classes: dict[str, ClassResult], label: str) -> ClassResult:
    return classes.setdefault(label, ClassResult(label=label))


def score_humanitarian() -> FileReport:
    from core.intel.geoextract import is_distress

    rows = _load_jsonl("humanitarian.jsonl")
    report = FileReport(filename="humanitarian.jsonl", scored=True, total=len(rows))
    cls = _record(report.classes, "is_distress")
    for row in rows:
        expected = bool(row["expected_is_distress"])
        actual = is_distress(row["input"])
        if expected and actual:
            cls.true_positives += 1
        elif expected and not actual:
            cls.false_negatives += 1
            cls.fn_ids.append(row["id"])
        elif not expected and actual:
            cls.false_positives += 1
            cls.fp_ids.append(row["id"])
        else:
            cls.true_negatives += 1
    return report


def score_humanitarian_recognition() -> FileReport:
    """docs/fixes.md M2.1: score core.intel.humanitarian_recognition.assess()
    against the same humanitarian.jsonl corpus, on the four dimensions the
    M2.1 exit gate names -- case_type, lifecycle, count accuracy, and
    publication recommendation. A separate report from score_humanitarian()
    above (which only ever scored the older is_distress() prefilter) so
    neither scorer's meaning drifts by being silently overloaded.

    expected_lifecycle: null means "not scored for this row" -- every
    non-operational hard negative in the corpus uses this (there is no
    single canonical lifecycle value for a report that never becomes an
    operational incident), same convention the corpus already used before
    this scorer existed to read it.
    """
    from core.intel.humanitarian_recognition import assess

    rows = _load_jsonl("humanitarian.jsonl")
    report = FileReport(filename="humanitarian.jsonl (recognition v2)", scored=True, total=len(rows))

    case_cls = _record(report.classes, "case_type")
    lifecycle_cls = _record(report.classes, "lifecycle")
    publication_cls = _record(report.classes, "publication_recommendation")
    counts_cls = _record(report.classes, "people_counts")

    for row in rows:
        if "expected_case_type" not in row:
            # Pre-M2.1 rows without the richer schema -- not this scorer's
            # concern; score_humanitarian() above still covers them.
            continue
        result = assess(row["input"])
        row_id = row["id"]

        if result.case_type == row["expected_case_type"]:
            case_cls.true_positives += 1
        else:
            case_cls.false_negatives += 1
            case_cls.fn_ids.append(row_id)

        expected_lifecycle = row.get("expected_lifecycle")
        if expected_lifecycle is not None:
            if result.lifecycle == expected_lifecycle:
                lifecycle_cls.true_positives += 1
            else:
                lifecycle_cls.false_negatives += 1
                lifecycle_cls.fn_ids.append(row_id)

        if result.publication_recommendation == row.get("expected_publication"):
            publication_cls.true_positives += 1
        else:
            publication_cls.false_negatives += 1
            publication_cls.fn_ids.append(row_id)

        actual_counts = {k: v for k, v in asdict(result.people).items() if v is not None}
        if actual_counts == row.get("expected_counts", {}):
            counts_cls.true_positives += 1
        else:
            counts_cls.false_negatives += 1
            counts_cls.fn_ids.append(row_id)

    return report


def score_ais_status() -> FileReport:
    from core.intel.service_taxonomy import classify_service

    rows = _load_jsonl("ais_status.jsonl")
    report = FileReport(filename="ais_status.jsonl", scored=True, total=len(rows))
    # One class per (service, lane) pair we expect to be able to hit, plus
    # "publishable" scored as its own boolean class -- a fail-closed
    # service=None classification is itself a meaningful, testable outcome.
    for row in rows:
        result = classify_service(row["input"])
        expected_key = f"service={row['expected_service']}/lane={row['expected_lane']}"
        actual_key = f"service={result.service}/lane={result.lane}"
        cls = _record(report.classes, expected_key)
        if actual_key == expected_key:
            cls.true_positives += 1
        else:
            cls.false_negatives += 1
            cls.fn_ids.append(row["id"])
            wrong_cls = _record(report.classes, actual_key)
            wrong_cls.false_positives += 1
            wrong_cls.fp_ids.append(row["id"])

        publishable_cls = _record(report.classes, "publishable")
        if bool(row["expected_publishable"]) == result.publishable:
            if result.publishable:
                publishable_cls.true_positives += 1
            else:
                publishable_cls.true_negatives += 1
        elif result.publishable:
            publishable_cls.false_positives += 1
            publishable_cls.fp_ids.append(row["id"])
        else:
            publishable_cls.false_negatives += 1
            publishable_cls.fn_ids.append(row["id"])
    return report


def score_ais_behaviour() -> FileReport:
    """docs/fixes.md M4.1: score core.intel.ais_behaviour_replay.classify()
    against ais_behaviour.jsonl -- unscored until this module existed (see
    its own docstring for why). Two dimensions the fixture schema actually
    carries: classification-label accuracy (the "publication decision" --
    alertable or not, and as what) and whether the returned confidence
    falls inside the fixture's expected range.

    A row whose ``kind`` this v0 classifier doesn't implement yet
    (vessel_loiter) is reported as its own unscored_count, not silently
    dropped or forced through as a guess.
    """
    from core.intel.ais_behaviour_replay import classify

    rows = _load_jsonl("ais_behaviour.jsonl")
    report = FileReport(filename="ais_behaviour.jsonl", scored=True, total=len(rows))
    label_cls = _record(report.classes, "classification")
    confidence_cls = _record(report.classes, "confidence_in_range")

    for row in rows:
        try:
            label, confidence = classify(row["input"])
        except KeyError:
            report.unscored_count += 1
            continue
        row_id = row["id"]
        if label == row["expected_classification"]:
            label_cls.true_positives += 1
        else:
            label_cls.false_negatives += 1
            label_cls.fn_ids.append(row_id)

        lo, hi = row["expected_confidence_range"]
        if lo <= confidence <= hi:
            confidence_cls.true_positives += 1
        else:
            confidence_cls.false_negatives += 1
            confidence_cls.fn_ids.append(row_id)
    return report


def score_ais_integrity() -> FileReport:
    """docs/fixes.md M4.1/M4.3: score core.intel.ais_integrity_replay.classify()
    against ais_integrity.jsonl -- same two dimensions as score_ais_behaviour()
    above (classification-label accuracy, confidence-range membership).
    """
    from core.intel.ais_integrity_replay import classify

    rows = _load_jsonl("ais_integrity.jsonl")
    report = FileReport(filename="ais_integrity.jsonl", scored=True, total=len(rows))
    label_cls = _record(report.classes, "classification")
    confidence_cls = _record(report.classes, "confidence_in_range")

    for row in rows:
        try:
            label, confidence = classify(row["input"])
        except KeyError:
            report.unscored_count += 1
            continue
        row_id = row["id"]
        if label == row["expected_classification"]:
            label_cls.true_positives += 1
        else:
            label_cls.false_negatives += 1
            label_cls.fn_ids.append(row_id)

        lo, hi = row["expected_confidence_range"]
        if lo <= confidence <= hi:
            confidence_cls.true_positives += 1
        else:
            confidence_cls.false_negatives += 1
            confidence_cls.fn_ids.append(row_id)
    return report


def _unscored_report(filename: str) -> FileReport:
    rows = _load_jsonl(filename)
    return FileReport(filename=filename, scored=False, total=len(rows), unscored_count=len(rows))


_SCORERS: dict[str, Callable[[], FileReport]] = {
    "humanitarian.jsonl": score_humanitarian,
    "humanitarian.jsonl (recognition v2)": score_humanitarian_recognition,
    "ais_status.jsonl": score_ais_status,
    "ais_behaviour.jsonl": score_ais_behaviour,
    "ais_integrity.jsonl": score_ais_integrity,
}
_UNSCORED_FILES: list[str] = []


def run_all() -> list[FileReport]:
    reports = [scorer() for scorer in _SCORERS.values()]
    reports += [_unscored_report(name) for name in _UNSCORED_FILES]
    return reports


def render_report(reports: list[FileReport]) -> str:
    lines = ["# Alert Recognition Baseline", ""]
    for report in reports:
        lines.append(f"## {report.filename} ({report.total} fixtures)")
        lines.append("")
        if not report.scored:
            lines.append("NOT YET SCORED -- see module docstring. Fixtures committed, no classifier wired yet.")
            lines.append("")
            continue
        lines.append("| class | precision | recall | F1 | FP | FN |")
        lines.append("|---|---|---|---|---|---|")
        for label, cls in sorted(report.classes.items()):
            p = f"{cls.precision:.2f}" if cls.precision is not None else "n/a"
            r = f"{cls.recall:.2f}" if cls.recall is not None else "n/a"
            f1 = f"{cls.f1:.2f}" if cls.f1 is not None else "n/a"
            lines.append(f"| {label} | {p} | {r} | {f1} | {cls.false_positives} | {cls.false_negatives} |")
        lines.append("")
        if report.unscored_count:
            lines.append(
                f"{report.unscored_count} fixture(s) skipped -- kind not yet implemented by the classifier."
            )
            lines.append("")
        for label, cls in sorted(report.classes.items()):
            if cls.fp_ids:
                lines.append(f"False positives ({label}): {', '.join(cls.fp_ids)}")
            if cls.fn_ids:
                lines.append(f"False negatives ({label}): {', '.join(cls.fn_ids)}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_report(run_all()))
