# SPDX-License-Identifier: AGPL-3.0-or-later
"""V1 vs V2 image-pipeline benchmark (docs/prompt.md §11 / §12, audit BM-1).

No database, no network -- pure evaluation over a set of images with ground
truth. `backfill_alarm_phone --benchmark` wires the CLI (JSON ground truth +
live media resolution) on top of this.

V1 is the raw coordinate core (`x_media_utils._extract_coordinate_from_bytes`
-- coordinate taken as-is). V2 is the structured pipeline
(`image_extraction.extract_from_bytes` -- confidence model + fail-closed
out-of-region rejection + pin-candidate detection). The disagreement list is
where V2's confidence model changed the outcome.

Precision is the headline: a false coordinate is worse than a missing one.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BenchmarkItem:
    name: str
    image_bytes: bytes
    image_kind: Optional[str] = None
    has_coordinate_text: bool = False
    has_pin: bool = False
    expected_coordinate: Optional[tuple[float, float]] = None  # (lat, lon)
    tolerance_km: float = 25.0


@dataclass
class PipelineMetrics:
    items: int = 0
    ocr_attempt_rate: float = 0.0
    coordinate_recall: float = 0.0        # correct within tolerance / expected-positive
    coordinate_precision: float = 0.0     # correct within tolerance / coordinates produced
    false_coordinate_rate: float = 0.0    # (out-of-tolerance + should-be-none) / produced
    median_error_km: Optional[float] = None
    pin_detection_recall: Optional[float] = None
    coordinates_produced: int = 0

    def as_dict(self) -> dict:
        return {
            "items": self.items,
            "ocr_attempt_rate": round(self.ocr_attempt_rate, 3),
            "coordinate_recall": round(self.coordinate_recall, 3),
            "coordinate_precision": round(self.coordinate_precision, 3),
            "false_coordinate_rate": round(self.false_coordinate_rate, 3),
            "median_error_km": (
                round(self.median_error_km, 1) if self.median_error_km is not None else None
            ),
            "pin_detection_recall": (
                round(self.pin_detection_recall, 3)
                if self.pin_detection_recall is not None
                else None
            ),
            "coordinates_produced": self.coordinates_produced,
        }


@dataclass
class BenchmarkReport:
    v1: PipelineMetrics
    v2: PipelineMetrics
    disagreements: list[dict] = field(default_factory=list)
    per_item: list[dict] = field(default_factory=list)

    def format_text(self) -> str:
        lines = ["image pipeline benchmark  (V1 = raw core, V2 = structured + confidence)", ""]
        keys = list(self.v1.as_dict())
        lines.append(f"{'metric':<24} {'V1':>10} {'V2':>10}")
        for key in keys:
            v1v, v2v = self.v1.as_dict()[key], self.v2.as_dict()[key]
            lines.append(f"{key:<24} {str(v1v):>10} {str(v2v):>10}")
        lines.append("")
        lines.append(f"V1/V2 disagreements: {len(self.disagreements)}")
        for d in self.disagreements:
            lines.append(f"  - {d['name']}: {d['note']}")
        return "\n".join(lines)


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def run_v1(image_bytes: bytes, *, executable: Optional[str] = None):
    """Raw coordinate core -- (coord, attempted, method)."""
    from core.intel.x_media_utils import _extract_coordinate_from_bytes

    coord, attempted, method, _diag = _extract_coordinate_from_bytes(
        image_bytes, executable=executable
    )
    return coord, attempted, method


def run_v2(image_bytes: bytes, *, executable: Optional[str] = None):
    """Structured pipeline -- ImageExtractionResult."""
    from core.intel.image_extraction import extract_from_bytes

    return extract_from_bytes(image_bytes, executable=executable)


def _score(
    outcomes: list[dict],
) -> PipelineMetrics:
    """outcomes: {expected, tolerance_km, has_pin, coord, attempted, pin_detected}."""
    n = len(outcomes)
    metrics = PipelineMetrics(items=n)
    if n == 0:
        return metrics

    metrics.ocr_attempt_rate = sum(1 for o in outcomes if o["attempted"]) / n

    produced = [o for o in outcomes if o["coord"] is not None]
    metrics.coordinates_produced = len(produced)
    positives = [o for o in outcomes if o["expected"] is not None]

    errors: list[float] = []
    correct = 0
    false_coords = 0
    for o in produced:
        if o["expected"] is None:
            false_coords += 1
            continue
        err = _haversine_km(o["coord"], o["expected"])
        errors.append(err)
        if err <= o["tolerance_km"]:
            correct += 1
        else:
            false_coords += 1

    if positives:
        metrics.coordinate_recall = correct / len(positives)
    if produced:
        metrics.coordinate_precision = correct / len(produced)
        metrics.false_coordinate_rate = false_coords / len(produced)
    if errors:
        metrics.median_error_km = statistics.median(errors)

    pin_items = [o for o in outcomes if o["has_pin"]]
    if pin_items:
        metrics.pin_detection_recall = sum(
            1 for o in pin_items if o["pin_detected"]
        ) / len(pin_items)
    return metrics


def evaluate(items: list[BenchmarkItem], *, executable: Optional[str] = None) -> BenchmarkReport:
    v1_outcomes: list[dict] = []
    v2_outcomes: list[dict] = []
    disagreements: list[dict] = []
    per_item: list[dict] = []

    for item in items:
        try:
            v1_coord, v1_attempted, v1_method = run_v1(item.image_bytes, executable=executable)
        except Exception:
            v1_coord, v1_attempted, v1_method = None, False, "error"
        try:
            v2 = run_v2(item.image_bytes, executable=executable)
            v2_coord = v2.selected_coordinate
            v2_attempted = v2.ocr_attempted
            v2_pin = v2.pin_detected
            v2_conf = v2.coordinate_confidence
        except Exception:
            v2_coord, v2_attempted, v2_pin, v2_conf = None, False, False, 0.0

        v1_outcomes.append({
            "expected": item.expected_coordinate,
            "tolerance_km": item.tolerance_km,
            "has_pin": item.has_pin,
            "coord": v1_coord,
            "attempted": v1_attempted,
            "pin_detected": "pin_landmark" in v1_method,
        })
        v2_outcomes.append({
            "expected": item.expected_coordinate,
            "tolerance_km": item.tolerance_km,
            "has_pin": item.has_pin,
            "coord": v2_coord,
            "attempted": v2_attempted,
            "pin_detected": v2_pin,
        })

        note = None
        if (v1_coord is None) != (v2_coord is None):
            note = (
                "V2 dropped a coordinate V1 kept"
                if v1_coord is not None
                else "V2 produced a coordinate V1 did not"
            )
        elif v1_coord is not None and v2_coord is not None:
            if _haversine_km(v1_coord, v2_coord) > max(1.0, item.tolerance_km):
                note = f"coordinates differ by {_haversine_km(v1_coord, v2_coord):.0f} km"
        if note:
            disagreements.append({
                "name": item.name,
                "v1_coord": v1_coord,
                "v2_coord": v2_coord,
                "expected": item.expected_coordinate,
                "note": note,
            })
        per_item.append({
            "name": item.name,
            "v1_method": v1_method,
            "v2_confidence": v2_conf,
            "v1_coord": v1_coord,
            "v2_coord": v2_coord,
        })

    return BenchmarkReport(
        v1=_score(v1_outcomes),
        v2=_score(v2_outcomes),
        disagreements=disagreements,
        per_item=per_item,
    )
