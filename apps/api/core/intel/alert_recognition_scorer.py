# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evaluation corpus scorer (docs/prompt.md Phase 3).

Scores ``tests/fixtures/alert_recognition/*.jsonl`` against whichever
deterministic classifiers already exist in this codebase, and reports
precision/recall/F1 per class plus explicit false-positive/false-negative
lists -- required before any detector threshold is touched (this session's
priority order; docs/prompt.md: "Do not claim an improvement unless the
evaluation corpus demonstrates it").

v0 scope: two of the four fixture files are actually scored today, against
functions that already exist as pure, callable classifiers:

  humanitarian.jsonl  -> core.intel.geoextract.is_distress(text)
  ais_status.jsonl    -> core.intel.service_taxonomy.classify_service(metadata)

``ais_behaviour.jsonl`` and ``ais_integrity.jsonl`` are present (full
schema, hard negatives from docs/prompt.md/fixes.md included) but not yet
scored -- AISSpikeDetector's sudden_stop/rescue_cluster/gap logic is
stateful and time-series-driven, not a pure ``classify(input) -> label``
function this scorer can call in isolation yet (docs/fixes.md Phase 7/8).
Each row in those two files is reported as ``not_yet_scored`` rather than
silently skipped, so the report is honest about what it did and did not
measure.

Run: ``python -m core.intel.alert_recognition_scorer``
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
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


def _unscored_report(filename: str) -> FileReport:
    rows = _load_jsonl(filename)
    return FileReport(filename=filename, scored=False, total=len(rows), unscored_count=len(rows))


_SCORERS: dict[str, Callable[[], FileReport]] = {
    "humanitarian.jsonl": score_humanitarian,
    "ais_status.jsonl": score_ais_status,
}
_UNSCORED_FILES = ["ais_behaviour.jsonl", "ais_integrity.jsonl"]


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
        for label, cls in sorted(report.classes.items()):
            if cls.fp_ids:
                lines.append(f"False positives ({label}): {', '.join(cls.fp_ids)}")
            if cls.fn_ids:
                lines.append(f"False negatives ({label}): {', '.join(cls.fn_ids)}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_report(run_all()))
