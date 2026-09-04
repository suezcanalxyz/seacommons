# SPDX-License-Identifier: AGPL-3.0-or-later
"""core.intel.image_extraction -- ImageExtractionResult orchestrator (docs/prompt.md §4).

The OCR engines are mocked at the x_media_utils seam (same approach as
test_x_media_utils.py) so these stay fast and deterministic; one real-OCR
smoke test runs only when RUN_OCR_TESTS=1.
"""
from __future__ import annotations

import os

import pytest
from core.intel import image_extraction, x_media_utils
from core.intel.image_extraction import (
    ImageExtractionResult,
    classify_image_kind,
    extract_from_bytes,
)

from tests.fixtures.alarm_phone_images import render_case


def _mock_engines(monkeypatch, *, easy_coord, easy_texts, coord_tuple):
    boxes = [{"text": t, "left": 0, "top": i * 20, "width": 40, "height": 12} for i, t in enumerate(easy_texts)]
    monkeypatch.setattr(
        x_media_utils, "_easyocr_image", lambda payload: (easy_coord, boxes, True)
    )
    monkeypatch.setattr(
        x_media_utils,
        "_extract_coordinate_from_bytes",
        lambda payload, *, executable=None, sea_snap=True: coord_tuple,
    )


def test_result_legacy_tuple_round_trips():
    result = ImageExtractionResult(
        selected_coordinate=(35.5, 24.9),
        coordinate_method="easyocr_tesseract_consensus",
        ocr_attempted=True,
    )
    result.diagnostics["interengine_distance_m"] = 120.0
    result.diagnostics["consensus_threshold_m"] = 500.0
    coord, attempted, method, diag = result.legacy_tuple()
    assert coord == (35.5, 24.9)
    assert attempted is True
    assert method == "easyocr_tesseract_consensus"
    assert diag == {"interengine_distance_m": 120.0, "consensus_threshold_m": 500.0}


def test_extract_keeps_place_names_and_distress_terms(monkeypatch):
    _mock_engines(
        monkeypatch,
        easy_coord=None,
        easy_texts=["47 people", "engine failure", "south of Lampedusa", "taking water"],
        coord_tuple=(None, True, "none", {}),
    )
    result = extract_from_bytes(render_case("text_card_people_and_condition"))
    assert "lampedusa" in result.place_names
    assert "engine failure" in result.distress_terms
    assert "taking water" in result.distress_terms
    assert result.selected_coordinate is None
    assert "no_coordinate" in result.failure_reasons
    assert result.as_metadata()["selected_method"] == "none"
    # docs/prompt.md §9: structured non-coordinate candidates, each with a span
    people = {p["kind"]: p for p in result.people_counts}
    assert people["aboard"]["count"] == 47
    assert {f["kind"] for f in result.vessel_conditions} >= {"engine_failure", "taking_water"}
    meta = result.as_metadata()
    assert meta["image_people_counts"][0]["raw"]
    assert "image_vessel_conditions" in meta


def test_extract_records_a_coordinate_candidate_and_confidence(monkeypatch):
    _mock_engines(
        monkeypatch,
        easy_coord=(34.27, 11.94),
        easy_texts=["N 34 16.292", "E 011 56.538"],
        coord_tuple=((34.27, 11.94), True, "easyocr_tesseract_consensus", {
            "interengine_distance_m": 90.0, "consensus_threshold_m": 500.0,
        }),
    )
    result = extract_from_bytes(render_case("coordinate_popup_dmm"))
    assert result.selected_coordinate == (34.27, 11.94)
    assert len(result.coordinate_candidates) == 1
    assert result.coordinate_candidates[0].source == "ocr_text"
    assert result.coordinate_method_family == "ocr_consensus"
    assert result.coordinate_confidence >= 0.8
    assert result.as_metadata()["image_sha256"]
    assert result.evidence["image_sha256"]


def test_caption_context_validates_but_never_moves_the_coordinate(monkeypatch):
    """docs/prompt.md §8: caption place names change the confidence, never the
    coordinate. A run with matching context and one without must select the
    exact same lat/lon."""
    def _run(context):
        _mock_engines(
            monkeypatch,
            easy_coord=(35.02, 12.18),
            easy_texts=["N 35 01.200", "E 012 10.800"],
            coord_tuple=((35.02, 12.18), True, "easyocr_tesseract_consensus", {
                "interengine_distance_m": 80.0, "consensus_threshold_m": 500.0,
            }),
        )
        return extract_from_bytes(render_case("pin_only_red"), context_places=context)

    near = _run(("lampedusa",))       # ~40 km away
    none = _run(())
    assert near.selected_coordinate == none.selected_coordinate == (35.02, 12.18)
    assert near.coordinate_confidence >= none.coordinate_confidence
    assert near.diagnostics["context_proximity_km"] < 120


def test_caption_far_from_coordinate_lowers_confidence(monkeypatch):
    _mock_engines(
        monkeypatch,
        easy_coord=(35.02, 12.18),
        easy_texts=["N 35 01.200", "E 012 10.800"],
        coord_tuple=((35.02, 12.18), True, "easyocr_tesseract_consensus", {
            "interengine_distance_m": 80.0, "consensus_threshold_m": 500.0,
        }),
    )
    # caption names a far-away place; the coordinate is not moved, only doubted
    far = extract_from_bytes(render_case("pin_only_red"), context_places=("lesvos",))
    assert far.selected_coordinate == (35.02, 12.18)
    assert far.confidence_components["context_agreement"] < 0.5


def test_out_of_region_coordinate_fails_closed(monkeypatch):
    """A coordinate outside the operational envelope (here mid-Indian-Ocean)
    is dropped -- selected_coordinate None, method 'none', reason recorded --
    so the caller keeps its fallback rather than plot a wrong distress pin
    (docs/prompt.md §5 / §13)."""
    _mock_engines(
        monkeypatch,
        easy_coord=(-8.0, 78.0),
        easy_texts=["S 08 00.000", "E 078 00.000"],
        coord_tuple=((-8.0, 78.0), True, "easyocr_tesseract_consensus", {
            "interengine_distance_m": 40.0, "consensus_threshold_m": 500.0,
        }),
    )
    result = extract_from_bytes(render_case("coordinate_popup_dmm"))
    assert result.selected_coordinate is None
    assert result.coordinate_method == "none"
    assert "coordinate_out_of_operational_region" in result.failure_reasons
    assert result.coordinate_confidence == 0.0


def test_disputed_read_gets_near_zero_confidence(monkeypatch):
    _mock_engines(
        monkeypatch,
        easy_coord=(34.27, 11.94),
        easy_texts=["garbled"],
        coord_tuple=((34.27, 11.94), True, "easyocr_text_disputed", {
            "interengine_distance_m": 1800.0, "consensus_threshold_m": 500.0,
        }),
    )
    result = extract_from_bytes(render_case("coordinate_popup_dmm"))
    assert result.coordinate_method_family == "ocr_disputed"
    assert result.coordinate_confidence < 0.2


def test_context_place_overlap_is_recorded_not_used_to_move_the_pin(monkeypatch):
    _mock_engines(
        monkeypatch,
        easy_coord=(34.27, 11.94),
        easy_texts=["Lampedusa", "Malta"],
        coord_tuple=((34.27, 11.94), True, "text", {}),
    )
    result = extract_from_bytes(
        render_case("coordinate_popup_dmm"), context_places=("lampedusa", "sfax")
    )
    assert result.diagnostics["context_place_overlap"] == ["lampedusa"]
    # the coordinate is unchanged -- context validates, never moves
    assert result.selected_coordinate == (34.27, 11.94)


def test_classify_image_kind_text_card_vs_map():
    text_card = render_case("text_card_people_and_condition")
    photo = render_case("photo_not_a_map")
    assert classify_image_kind(text_card, easyocr_box_count=6, has_pin=False, has_coordinate=False) == "text_card"
    assert classify_image_kind(photo, easyocr_box_count=0, has_pin=False, has_coordinate=False) == "photo"
    map_png = render_case("pin_only_red")
    assert classify_image_kind(map_png, easyocr_box_count=5, has_pin=True, has_coordinate=False) == "map_screenshot"


def test_extract_from_bytes_handles_undecodable_payload():
    result = extract_from_bytes(b"not-an-image")
    assert "image_decode_failed" in result.failure_reasons
    assert result.selected_coordinate is None


@pytest.mark.skipif(os.getenv("RUN_OCR_TESTS") != "1", reason="real OCR is slow")
def test_real_ocr_reads_the_dmm_popup():
    result = image_extraction.extract_from_bytes(render_case("coordinate_popup_dmm"))
    assert result.selected_coordinate is not None
    lat, lon = result.selected_coordinate
    assert abs(lat - 34.2715) < 0.05 and abs(lon - 11.9423) < 0.05
