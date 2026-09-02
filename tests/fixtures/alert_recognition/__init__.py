# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alert-recognition evaluation corpus + scorer (docs/prompt.md PHASE 3, audit EV-1).

Four labelled `.jsonl` files -- `humanitarian`, `ais_status`, `ais_behaviour`,
`ais_integrity` -- each row an `input` observation and the `expected`
classification / lifecycle / entities / publication decision / confidence
range, plus `notes`. Hard negatives are included on purpose ("annual report"
is not distress, "moored in Valletta" is not a sudden stop, a feed-wide
outage is not N vessel gaps).

`score()` turns a list of predictions into per-class precision / recall / F1 /
FP / FN and the publication-decision accuracy. The V2 recognition PRs
(EventAssessment, HumanitarianAssessment, the AIS re-audits) each run their
classifier through this and must not claim an improvement the corpus does not
show.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DIR = Path(__file__).parent
CORPUS_NAMES = ("humanitarian", "ais_status", "ais_behaviour", "ais_integrity")

_REQUIRED_KEYS = {"id", "input", "expected", "notes"}
_REQUIRED_EXPECTED_KEYS = {"classification", "lifecycle", "publication", "confidence_range"}
_PUBLICATION_VALUES = {"published", "internal", "private"}


@dataclass(frozen=True)
class CorpusRow:
    id: str
    corpus: str
    input: dict[str, Any]
    classification: str
    lifecycle: str
    entities: dict[str, Any]
    publication: str
    confidence_range: tuple[float, float]
    notes: str
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def expects_no_alert(self) -> bool:
        """Should produce no operational classification at all."""
        return self.classification == "none"

    @property
    def is_contrastive_negative(self) -> bool:
        """A row that must NOT get the tempting wrong class (may still get a
        correct, less-alarming one -- e.g. a feed outage classed coverage_gap,
        not vessel_gap)."""
        return self.notes.upper().startswith("HARD NEGATIVE")


def load_corpus(name: str) -> list[CorpusRow]:
    path = _DIR / f"{name}.jsonl"
    rows: list[CorpusRow] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:  # pragma: no cover - guarded by a test
            raise ValueError(f"{name}.jsonl:{line_no}: invalid JSON ({exc})") from exc
        missing = _REQUIRED_KEYS - obj.keys()
        if missing:
            raise ValueError(f"{name}.jsonl:{line_no}: missing keys {sorted(missing)}")
        exp = obj["expected"]
        exp_missing = _REQUIRED_EXPECTED_KEYS - exp.keys()
        if exp_missing:
            raise ValueError(f"{name}.jsonl:{line_no}: expected missing {sorted(exp_missing)}")
        if exp["publication"] not in _PUBLICATION_VALUES:
            raise ValueError(f"{name}.jsonl:{line_no}: bad publication {exp['publication']!r}")
        lo, hi = exp["confidence_range"]
        if not (0.0 <= lo <= hi <= 1.0):
            raise ValueError(f"{name}.jsonl:{line_no}: bad confidence_range {exp['confidence_range']}")
        rows.append(
            CorpusRow(
                id=obj["id"],
                corpus=name,
                input=obj["input"],
                classification=exp["classification"],
                lifecycle=exp["lifecycle"],
                entities=exp.get("entities", {}),
                publication=exp["publication"],
                confidence_range=(float(lo), float(hi)),
                notes=obj["notes"],
                extra={k: v for k, v in exp.items() if k not in _REQUIRED_EXPECTED_KEYS | {"entities"}},
            )
        )
    return rows


def load_all() -> list[CorpusRow]:
    return [row for name in CORPUS_NAMES for row in load_corpus(name)]


@dataclass
class ClassScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp, "fp": self.fp, "fn": self.fn,
            "precision": round(self.precision, 3),
            "recall": round(self.recall, 3),
            "f1": round(self.f1, 3),
        }


@dataclass
class RecognitionReport:
    per_class: dict[str, ClassScore]
    publication_accuracy: float
    lifecycle_accuracy: float
    confidence_in_range: float
    n: int
    mismatches: list[dict[str, Any]] = field(default_factory=list)

    def macro_f1(self) -> float:
        real = [s for cls, s in self.per_class.items() if cls != "none"]
        return round(sum(s.f1 for s in real) / len(real), 3) if real else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "macro_f1": self.macro_f1(),
            "publication_accuracy": round(self.publication_accuracy, 3),
            "lifecycle_accuracy": round(self.lifecycle_accuracy, 3),
            "confidence_in_range": round(self.confidence_in_range, 3),
            "per_class": {cls: s.as_dict() for cls, s in sorted(self.per_class.items())},
        }


def score(rows: list[CorpusRow], predictions: dict[str, dict[str, Any]]) -> RecognitionReport:
    """`predictions[row.id]` = {classification, lifecycle?, publication?, confidence?}."""
    per_class: dict[str, ClassScore] = defaultdict(ClassScore)
    pub_ok = life_ok = conf_ok = 0
    mismatches: list[dict[str, Any]] = []

    for row in rows:
        pred = predictions.get(row.id, {})
        predicted = pred.get("classification", "none")
        if predicted == row.classification:
            per_class[row.classification].tp += 1
        else:
            per_class[predicted].fp += 1
            per_class[row.classification].fn += 1
            mismatches.append(
                {"id": row.id, "expected": row.classification, "predicted": predicted}
            )

        if "publication" in pred:
            pub_ok += int(pred["publication"] == row.publication)
        if "lifecycle" in pred:
            life_ok += int(pred["lifecycle"] == row.lifecycle)
        if "confidence" in pred:
            lo, hi = row.confidence_range
            conf_ok += int(lo <= float(pred["confidence"]) <= hi)

    n = len(rows) or 1
    return RecognitionReport(
        per_class=dict(per_class),
        publication_accuracy=pub_ok / n,
        lifecycle_accuracy=life_ok / n,
        confidence_in_range=conf_ok / n,
        n=len(rows),
        mismatches=mismatches,
    )


def run(classify: Callable[[CorpusRow], dict[str, Any]], rows: list[CorpusRow] | None = None) -> RecognitionReport:
    """Convenience: call `classify` on every row and score the result."""
    rows = rows if rows is not None else load_all()
    predictions = {row.id: classify(row) for row in rows}
    return score(rows, predictions)
