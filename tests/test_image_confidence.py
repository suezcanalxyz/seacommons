# SPDX-License-Identifier: AGPL-3.0-or-later
"""core.intel.image_confidence -- traceable coordinate confidence (docs/prompt.md §5)."""
from __future__ import annotations

from core.intel.image_confidence import (
    ConfidenceComponents,
    combined_confidence,
    score_coordinate,
)
from core.intel.location_evidence import evidence_from_ocr_method


def _boxes(*texts, confidence=0.95):
    return [{"text": t, "confidence": confidence} for t in texts]


def test_consensus_in_region_with_agreeing_engines_scores_high():
    components = score_coordinate(
        "ocr_consensus",
        lat=34.27,
        lon=11.94,
        interengine_distance_m=90.0,
        easy_boxes=_boxes("N 34 16.292", "E 011 56.538"),
    )
    assert components.region_validity == 1.0
    assert components.engine_agreement == 1.0
    assert combined_confidence(components, "ocr_consensus") >= 0.8


def test_out_of_region_coordinate_scores_zero():
    components = score_coordinate(
        "ocr_consensus", lat=-12.0, lon=77.0, interengine_distance_m=10.0
    )
    assert components.region_validity == 0.0
    assert components.score() == 0.0
    assert combined_confidence(components, "ocr_consensus") == 0.0


def test_disputed_read_is_capped_near_zero_regardless_of_components():
    components = score_coordinate(
        "ocr_disputed", lat=34.27, lon=11.94, interengine_distance_m=1800.0
    )
    assert combined_confidence(components, "ocr_disputed") <= 0.12


def test_single_engine_is_mid_confidence():
    components = score_coordinate("ocr_single_engine", lat=35.0, lon=13.0)
    score = combined_confidence(components, "ocr_single_engine")
    assert 0.35 <= score <= 0.7


def test_engine_disagreement_distance_lowers_agreement():
    close = score_coordinate("ocr_consensus", lat=35.0, lon=13.0, interengine_distance_m=100.0)
    far = score_coordinate("ocr_consensus", lat=35.0, lon=13.0, interengine_distance_m=1500.0)
    assert close.engine_agreement > far.engine_agreement


def test_pin_solver_confidence_becomes_parser_validity():
    components = score_coordinate(
        "pin_landmark", lat=35.0, lon=13.0, pin_solver_confidence=0.62
    )
    assert components.parser_validity == 0.62


def test_context_overlap_is_a_bounded_bonus_not_a_penalty():
    with_ctx = score_coordinate("ocr_consensus", lat=35.0, lon=13.0, context_overlap=["sfax"])
    without = score_coordinate("ocr_consensus", lat=35.0, lon=13.0, context_overlap=[])
    assert with_ctx.context_agreement > without.context_agreement
    assert without.context_agreement == 0.5  # absence is neutral


def test_components_serialise():
    d = ConfidenceComponents(parser_validity=0.9).as_dict()
    assert set(d) == {
        "parser_validity", "engine_agreement", "ocr_confidence",
        "region_validity", "context_agreement", "landmask_validity",
    }


def test_estimated_error_only_widens_uncertainty():
    # pin fallback constant is 4000 m; a tighter fit estimate must not shrink it
    tight = evidence_from_ocr_method(
        "easyocr_pin_landmark", 35.0, 13.0, estimated_position_error_m=800.0
    )
    assert tight.uncertainty_m == 4000.0
    # a wider estimate wins
    wide = evidence_from_ocr_method(
        "easyocr_pin_landmark", 35.0, 13.0, estimated_position_error_m=9000.0
    )
    assert wide.uncertainty_m == 9000.0


def test_estimated_error_never_shrinks_a_consensus_radius():
    ev = evidence_from_ocr_method(
        "easyocr_tesseract_consensus", 35.0, 13.0, estimated_position_error_m=50.0
    )
    assert ev.uncertainty_m == 400.0
