# SPDX-License-Identifier: AGPL-3.0-or-later
"""core.intel.image_benchmark -- V1/V2 comparison (docs/prompt.md §11 / §12)."""
from __future__ import annotations

import os

import pytest
from core.intel import image_benchmark
from core.intel.image_benchmark import BenchmarkItem, evaluate

from tests.fixtures.alarm_phone_images import CASES


def _canned(monkeypatch, v1_map, v2_map):
    """v1_map: name -> (coord, attempted, method); v2_map: name -> (coord, attempted, pin)."""
    calls = {"i": 0}
    order = [item.name for item in _ITEMS]

    def fake_v1(image_bytes, *, executable=None):
        return v1_map[order[calls["i"]]]

    def fake_v2(image_bytes, *, executable=None):
        name = order[calls["i"]]
        calls["i"] += 1
        coord, attempted, pin = v2_map[name]
        return _Result(coord, attempted, pin)

    monkeypatch.setattr(image_benchmark, "run_v1", fake_v1)
    monkeypatch.setattr(image_benchmark, "run_v2", fake_v2)


class _Result:
    def __init__(self, coord, attempted, pin):
        self.selected_coordinate = coord
        self.ocr_attempted = attempted
        self.pin_detected = pin
        self.coordinate_confidence = 0.8 if coord else 0.0


_ITEMS = [
    BenchmarkItem("hit", b"x", expected_coordinate=(35.0, 12.0), tolerance_km=5.0, has_pin=False),
    BenchmarkItem("miss", b"x", expected_coordinate=(40.0, 20.0), tolerance_km=5.0, has_pin=True),
    BenchmarkItem("should_be_none", b"x", expected_coordinate=None, has_pin=False),
]


def test_metric_math(monkeypatch):
    _canned(
        monkeypatch,
        v1_map={
            "hit": ((35.01, 12.0), True, "easyocr_tesseract_consensus"),
            "miss": ((10.0, 10.0), True, "easyocr_pin_landmark"),   # far off
            "should_be_none": ((1.0, 1.0), True, "easyocr_text"),   # false coordinate
        },
        v2_map={
            "hit": ((35.01, 12.0), True, False),
            "miss": (None, True, True),           # V2 dropped the bad one, still detected the pin
            "should_be_none": (None, True, False),  # V2 failed closed
        },
    )
    report = evaluate(_ITEMS)

    # V1: 3 coords produced, 1 correct -> precision 1/3, 2 false -> 2/3
    assert report.v1.coordinates_produced == 3
    assert report.v1.coordinate_precision == pytest.approx(1 / 3, abs=0.01)
    assert report.v1.false_coordinate_rate == pytest.approx(2 / 3, abs=0.01)
    assert report.v1.coordinate_recall == pytest.approx(0.5, abs=0.01)  # 1 of 2 positives

    # V2: 1 coord produced, correct -> precision 1.0, 0 false
    assert report.v2.coordinates_produced == 1
    assert report.v2.coordinate_precision == 1.0
    assert report.v2.false_coordinate_rate == 0.0

    # pin recall: one has_pin item ("miss"); V1 method has pin_landmark, V2 pin_detected
    assert report.v1.pin_detection_recall == 1.0
    assert report.v2.pin_detection_recall == 1.0


def test_disagreements_are_listed(monkeypatch):
    _canned(
        monkeypatch,
        v1_map={
            "hit": ((35.0, 12.0), True, "easyocr_text"),
            "miss": ((40.0, 20.0), True, "easyocr_text"),
            "should_be_none": ((1.0, 1.0), True, "easyocr_text"),
        },
        v2_map={
            "hit": ((35.0, 12.0), True, False),
            "miss": ((40.0, 20.0), True, False),
            "should_be_none": (None, True, False),   # the one disagreement
        },
    )
    report = evaluate(_ITEMS)
    assert len(report.disagreements) == 1
    assert report.disagreements[0]["name"] == "should_be_none"
    assert "V2 dropped" in report.disagreements[0]["note"]
    assert "disagreements: 1" in report.format_text()


@pytest.mark.skipif(os.getenv("RUN_OCR_TESTS") != "1", reason="real OCR is slow")
def test_real_pipeline_over_the_fixture_corpus():
    items = [
        BenchmarkItem(
            name=c.name,
            image_bytes=c.render(),
            image_kind=c.image_kind,
            has_coordinate_text=c.has_coordinate_text,
            has_pin=c.has_pin,
            expected_coordinate=c.expected_coordinate,
            tolerance_km=c.tolerance_km,
        )
        for c in CASES
    ]
    report = evaluate(items)
    # the whole point of V2: it must not be less precise than V1
    assert report.v2.false_coordinate_rate <= report.v1.false_coordinate_rate + 1e-9
