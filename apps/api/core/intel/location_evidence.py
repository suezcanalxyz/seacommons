# SPDX-License-Identifier: AGPL-3.0-or-later
"""One shared representation of an extracted location's evidence quality.

docs/fixes.md F-04 / F-05 / Phase 1.1: OCR-method-string -> (coordinate_source,
uncertainty, review_status) semantics were duplicated -- and had already
diverged -- between core.intel.twikit_monitor._apply_media_ocr (live) and
core.intel.backfill_alarm_phone.apply_position (historical). A disputed or
lone-engine coordinate could also outrank a verified one because upgrade
decisions compared source rank alone. This module is the single place both
concerns are defined.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LocationEvidence:
    """An extracted coordinate plus everything needed to judge its quality."""

    lat: float | None = None
    lon: float | None = None
    coordinate_source: str = "none"
    review_status: str = "not_required"
    uncertainty_m: float | None = None
    engine: str | None = None
    raw_coordinate_text: str | None = None
    normalized_coordinate_text: str | None = None
    interengine_distance_m: float | None = None
    media_sha256: str | None = None
    source_post_id: str | None = None
    media_index: int | None = None
    review_required: bool = False

    def as_metadata(self) -> dict[str, Any]:
        """The IntelEvent.metadata subset live ingestion and backfill both write."""
        meta: dict[str, Any] = {
            "coordinate_source": self.coordinate_source,
            "coordinate_review_status": self.review_status,
            "verification_status": "machine_extracted_unverified",
            "location_uncertainty_m": self.uncertainty_m,
        }
        for key, value in (
            ("ocr_engine", self.engine),
            ("ocr_coordinate_raw", self.raw_coordinate_text),
            ("ocr_coordinate_normalized", self.normalized_coordinate_text),
            ("ocr_interengine_distance_m", self.interengine_distance_m),
            ("media_sha256", self.media_sha256),
            ("source_post_id", self.source_post_id),
            ("media_index", self.media_index),
        ):
            if value is not None:
                meta[key] = value
        return meta

    def quality(self) -> tuple[int, int, float]:
        return location_quality(
            self.coordinate_source, self.review_status, self.uncertainty_m
        )


# ── OCR method -> evidence semantics (the one definition) ─────────────────────
_OCR_METHOD_EVIDENCE: dict[str, tuple[str, float, str, bool]] = {
    # method                       coordinate_source      uncertainty  review_status                     review_required
    "easyocr_tesseract_consensus": ("media_ocr_consensus", 400.0, "machine_ocr_consensus_verified", False),
    "easyocr_text_disputed":       ("media_ocr_text", 3500.0, "machine_ocr_disputed_needs_review", True),
}
_OCR_TEXT_FALLBACK = ("media_ocr_text", 1500.0, "machine_ocr_unverified", True)
_OCR_PIN_FALLBACK = ("media_pin_landmark", 4000.0, "machine_ocr_unverified", True)


def evidence_from_ocr_method(
    method: str,
    lat: float | None,
    lon: float | None,
    *,
    engine: str | None = None,
    **extra: Any,
) -> LocationEvidence:
    """Build a LocationEvidence from an _ocr_photo() method string.

    Mirrors the historical live-ingestion mapping exactly; a lone-engine text
    read stays at the conservative constant, two engines agreeing earns the
    tight radius, a disagreement is wide + needs review.
    """
    key = (method or "").lower()
    if key in _OCR_METHOD_EVIDENCE:
        source, uncertainty, review, review_required = _OCR_METHOD_EVIDENCE[key]
    elif key.endswith("text"):
        source, uncertainty, review, review_required = _OCR_TEXT_FALLBACK
    else:
        source, uncertainty, review, review_required = _OCR_PIN_FALLBACK
    resolved_engine = engine or ("easyocr" if key.startswith("easyocr") else "tesseract")
    return LocationEvidence(
        lat=lat,
        lon=lon,
        coordinate_source=source,
        review_status=review,
        uncertainty_m=uncertainty,
        engine=resolved_engine,
        review_required=review_required,
        **extra,
    )


def ocr_result_label(method: str) -> str:
    """Low-cardinality metric label for an OCR method (core.observability)."""
    key = (method or "").lower()
    if key == "easyocr_tesseract_consensus":
        return "consensus"
    if key == "easyocr_text_disputed":
        return "disputed"
    if key.endswith("text"):
        return "text_unverified"
    return "pin_landmark"


# ── Evidence-quality ordering (docs/fixes.md F-04) ───────────────────────────
# Review status dominates: a disputed / lone-engine coordinate can be stored
# for review but must never *supersede* a verified one, regardless of source.
_REVIEW_RANK: dict[str, int] = {
    "human_verified": 5,
    "reported_exact": 5,
    "not_required": 4,
    "machine_ocr_consensus_verified": 3,
    "machine_ocr_unverified": 1,
    "machine_ocr_disputed_needs_review": 0,
}
_SOURCE_RANK: dict[str, int] = {
    "": 0,
    "none": 0,
    "place_centroid": 1,
    "region_area": 1,
    "relative_place_offset": 2,
    "media_pin_landmark": 3,
    "media_ocr_consensus": 4,
    "media_ocr_text": 4,
    "navtext": 5,
    "ais_position": 6,
    "post_text": 6,
}
_DEFAULT_REVIEW_RANK = 2
_DEFAULT_SOURCE_RANK = 2


def location_quality(
    coordinate_source: str | None,
    review_status: str | None,
    uncertainty_m: float | None = None,
) -> tuple[int, int, float]:
    """A sortable quality key -- higher is better evidence.

    Ordered by (review-status rank, source rank, tighter uncertainty). The
    review-status term comes first so no coarser-but-"higher-source" reading
    can ever replace a verified coordinate.
    """
    review = _REVIEW_RANK.get(str(review_status or "").lower(), _DEFAULT_REVIEW_RANK)
    source = _SOURCE_RANK.get(str(coordinate_source or "none").lower(), _DEFAULT_SOURCE_RANK)
    try:
        neg_uncertainty = -float(uncertainty_m) if uncertainty_m is not None else -1e12
    except (TypeError, ValueError):
        neg_uncertainty = -1e12
    return (review, source, neg_uncertainty)
