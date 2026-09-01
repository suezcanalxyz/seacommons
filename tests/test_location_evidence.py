# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md F-04 / F-05 / Phase 1.1 -- one shared location-evidence model.

OCR-method semantics must be identical for live ingestion and backfill, and a
disputed / unverified coordinate must never *supersede* a verified one.
"""
from __future__ import annotations

from core.intel.location_evidence import (
    LocationEvidence,
    evidence_from_ocr_method,
    location_quality,
    ocr_result_label,
)


def test_ocr_method_mapping_matches_the_historical_live_constants():
    consensus = evidence_from_ocr_method("easyocr_tesseract_consensus", 34.0, 12.0)
    assert consensus.coordinate_source == "media_ocr_consensus"
    assert consensus.uncertainty_m == 400.0
    assert consensus.review_status == "machine_ocr_consensus_verified"
    assert consensus.review_required is False

    disputed = evidence_from_ocr_method("easyocr_text_disputed", 34.0, 12.0)
    assert disputed.coordinate_source == "media_ocr_text"
    assert disputed.uncertainty_m == 3500.0
    assert disputed.review_status == "machine_ocr_disputed_needs_review"
    assert disputed.review_required is True

    text = evidence_from_ocr_method("tesseract_text", 34.0, 12.0)
    assert text.coordinate_source == "media_ocr_text"
    assert text.uncertainty_m == 1500.0
    assert text.review_status == "machine_ocr_unverified"

    pin = evidence_from_ocr_method("pin_landmark", 34.0, 12.0)
    assert pin.coordinate_source == "media_pin_landmark"
    assert pin.uncertainty_m == 4000.0
    assert pin.review_status == "machine_ocr_unverified"


def test_engine_is_inferred_from_the_method_prefix():
    assert evidence_from_ocr_method("easyocr_text", 0, 0).engine == "easyocr"
    assert evidence_from_ocr_method("tesseract_text", 0, 0).engine == "tesseract"
    assert evidence_from_ocr_method("text", 0, 0, engine="easyocr").engine == "easyocr"


def test_as_metadata_only_emits_present_fields():
    meta = LocationEvidence(
        coordinate_source="media_ocr_consensus",
        review_status="machine_ocr_consensus_verified",
        uncertainty_m=400.0,
        engine="tesseract",
        interengine_distance_m=210.0,
    ).as_metadata()
    assert meta["coordinate_source"] == "media_ocr_consensus"
    assert meta["ocr_interengine_distance_m"] == 210.0
    assert "media_sha256" not in meta
    assert "source_post_id" not in meta


def test_disputed_coordinate_never_outranks_a_verified_one():
    verified = location_quality("media_ocr_consensus", "machine_ocr_consensus_verified", 400)
    disputed = location_quality("media_ocr_text", "machine_ocr_disputed_needs_review", 3500)
    unverified = location_quality("media_ocr_text", "machine_ocr_unverified", 1500)
    text = location_quality("post_text", "not_required", 250)

    assert disputed < unverified < verified < text


def test_tighter_uncertainty_breaks_a_same_status_tie():
    tight = location_quality("media_ocr_text", "machine_ocr_unverified", 800)
    loose = location_quality("media_ocr_text", "machine_ocr_unverified", 4000)
    assert loose < tight


def test_ocr_result_label():
    assert ocr_result_label("easyocr_tesseract_consensus") == "consensus"
    assert ocr_result_label("easyocr_text_disputed") == "disputed"
    assert ocr_result_label("tesseract_text") == "text_unverified"
    assert ocr_result_label("pin_landmark") == "pin_landmark"
