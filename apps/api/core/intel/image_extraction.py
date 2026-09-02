# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured image understanding for tracked X/Twitter media (docs/prompt.md §4).

`x_media_utils._ocr_photo` answers exactly one question -- "coordinate or
None" -- and throws away everything else the pixels contain: what kind of
image it is, the place names on the basemap, a head count on a text card,
the pin geometry, the per-engine text. `ImageExtractionResult` keeps all of
it so the humanitarian classifier (and the benchmark) can use it, and so a
"no coordinate" outcome can be told apart from "corrupt download".

This module is additive. `_ocr_photo` stays a 4-tuple for
`twikit_monitor` / `backfill_alarm_phone` until they are migrated; the
coordinate it selects and the method string are produced by the same
`x_media_utils._extract_coordinate_from_bytes` core, so the two never
disagree.
"""
from __future__ import annotations

import hashlib
import io
import shutil
from dataclasses import dataclass, field
from typing import Any, Optional

# Referenced via the module (not `from ... import`) so a test that patches
# core.intel.x_media_utils._easyocr_image / _extract_coordinate_from_bytes
# reaches the call sites here too.
from core.intel import x_media_utils

ImageKind = str  # map_screenshot | text_card | infographic | photo | unknown

# OCR method -> the coarse acquisition method the structured result reports.
_METHOD_FAMILY = {
    "easyocr_tesseract_consensus": "ocr_consensus",
    "easyocr_text_disputed": "ocr_disputed",
    "easyocr_text": "ocr_single_engine",
    "text": "printed_text",
    "easyocr_pin_landmark": "pin_landmark",
    "tesseract_pin_landmark": "pin_landmark",
    "none": "none",
}


@dataclass
class CoordinateCandidate:
    lat: float
    lon: float
    method: str
    source: str  # ocr_text | pin_landmark


@dataclass
class ImageExtractionResult:
    image_kind: ImageKind = "unknown"
    detected_text: str = ""
    coordinate_candidates: list[CoordinateCandidate] = field(default_factory=list)
    selected_coordinate: Optional[tuple[float, float]] = None
    coordinate_method: str = "none"           # legacy method string (evidence semantics)
    coordinate_method_family: str = "none"    # coarse family
    coordinate_confidence: float = 0.0
    confidence_components: dict[str, float] = field(default_factory=dict)
    place_names: list[str] = field(default_factory=list)
    people_counts: list[dict[str, Any]] = field(default_factory=list)
    distress_terms: list[str] = field(default_factory=list)
    pin_detected: bool = False
    pin_candidates: list[dict[str, Any]] = field(default_factory=list)
    landmarks_used: list[str] = field(default_factory=list)
    landmarks_detected: list[str] = field(default_factory=list)
    fit_residual_px: Optional[float] = None
    estimated_position_error_m: Optional[float] = None
    ocr_engines: list[str] = field(default_factory=list)
    ocr_attempted: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    failure_reasons: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def legacy_tuple(
        self,
    ) -> tuple[Optional[tuple[float, float]], bool, str, dict[str, Any]]:
        """The 4-tuple shape twikit_monitor / backfill still consume."""
        return (
            self.selected_coordinate,
            self.ocr_attempted,
            self.coordinate_method,
            {
                key: value
                for key, value in self.diagnostics.items()
                if key in {"interengine_distance_m", "consensus_threshold_m"}
            },
        )

    def as_metadata(self) -> dict[str, Any]:
        """The §10 observability keys, for the event metadata envelope."""
        return {
            "image_kind": self.image_kind,
            "image_dimensions": self.diagnostics.get("image_dimensions"),
            "image_sha256": self.evidence.get("image_sha256"),
            "easyocr_box_count": self.diagnostics.get("easyocr_box_count", 0),
            "coordinate_candidate_count": len(self.coordinate_candidates),
            "pin_detected": self.pin_detected,
            "landmark_count": len(self.landmarks_detected),
            "selected_method": self.coordinate_method,
            "selected_method_family": self.coordinate_method_family,
            "image_place_names": self.place_names[:12],
            **({"image_failure_reasons": self.failure_reasons} if self.failure_reasons else {}),
        }


# ── image kind ──────────────────────────────────────────────────────────────
def classify_image_kind(
    payload: bytes,
    *,
    easyocr_box_count: int,
    has_pin: bool,
    has_coordinate: bool,
) -> ImageKind:
    """Coarse image-type classifier (refined in a later PR).

    A slippy-map screenshot has a blue-ish water region and scattered labels;
    a text card is a near-flat background with left-aligned lines; a photo is
    high-variance with little machine text.
    """
    try:
        import numpy as np
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(payload)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            pixels = np.asarray(image.resize((160, 160)))
    except Exception:
        return "unknown"

    r, g, b = (pixels[:, :, i].astype(int) for i in range(3))
    water = ((b > g) & (b > r) & (b > 110) & (b - r > 12)).mean()
    unique_rows = len({tuple(row) for row in pixels.reshape(-1, 3)[::7].tolist()})
    flatness = 1.0 - min(1.0, unique_rows / 3200)

    if has_pin or has_coordinate or (water > 0.12 and easyocr_box_count >= 3):
        return "map_screenshot"
    if easyocr_box_count >= 4 and flatness > 0.55:
        return "text_card"
    if easyocr_box_count >= 6 and flatness > 0.3:
        return "infographic"
    if easyocr_box_count <= 2:
        return "photo"
    return "unknown"


# ── place / people / distress extraction from OCR text ───────────────────────
def _place_names_from_text(text: str) -> list[str]:
    from core.intel.geoextract import find_all_place_matches

    return [name for name, _coords, _tier in find_all_place_matches(text)]


def _distress_terms_from_text(text: str) -> list[str]:
    from core.intel.geoextract import DISTRESS_KW

    lowered = text.lower()
    return sorted({term for term in DISTRESS_KW if term in lowered})


def _attach_pin_fit(result, payload, executable, easy_boxes) -> None:
    """Populate the Web-Mercator fit diagnostics for a pin-landmark result."""
    try:
        from core.intel.map_pin_geolocate import geolocate_pin_detailed

        solution = geolocate_pin_detailed(
            payload, executable=executable, word_boxes=easy_boxes or None
        )
    except Exception:
        solution = None
    if solution is None:
        return
    result.landmarks_used = list(solution.landmarks_used)
    result.landmarks_detected = list(solution.landmarks_detected)
    result.fit_residual_px = solution.fit_residual_px
    result.estimated_position_error_m = solution.estimated_position_error_m
    result.pin_candidates.append({"confidence": solution.confidence, "detector": "landmark_fit"})


# ── orchestrator ────────────────────────────────────────────────────────────
def extract_from_bytes(
    payload: bytes,
    *,
    executable: Optional[str] = None,
    context_places: tuple[str, ...] = (),
) -> ImageExtractionResult:
    result = ImageExtractionResult()
    result.evidence["image_sha256"] = hashlib.sha256(payload).hexdigest()

    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(payload)) as source:
            image = ImageOps.exif_transpose(source)
            result.diagnostics["image_dimensions"] = [image.width, image.height]
    except Exception:
        result.failure_reasons.append("image_decode_failed")
        return result

    easy_coordinate, easy_boxes, easy_attempted = x_media_utils._easyocr_image(payload)
    if easy_attempted:
        result.ocr_engines.append("easyocr")
    detected_text = "\n".join(box.get("text", "") for box in easy_boxes)
    result.detected_text = detected_text[:4000]
    result.diagnostics["easyocr_box_count"] = len(easy_boxes)

    executable = executable if executable is not None else shutil.which("tesseract")
    coordinate, attempted, method, diag = x_media_utils._extract_coordinate_from_bytes(
        payload, executable=executable
    )
    if executable and method.startswith(("text", "easyocr_tesseract", "easyocr_text_disputed")):
        result.ocr_engines.append("tesseract")
    result.ocr_attempted = bool(attempted or easy_attempted)
    result.coordinate_method = method
    result.coordinate_method_family = _METHOD_FAMILY.get(method, "none")
    result.diagnostics.update(diag)

    if coordinate is not None:
        source_kind = "pin_landmark" if "pin_landmark" in method else "ocr_text"
        result.selected_coordinate = coordinate
        result.coordinate_candidates.append(
            CoordinateCandidate(coordinate[0], coordinate[1], method, source_kind)
        )
        result.pin_detected = source_kind == "pin_landmark"
        if source_kind == "pin_landmark":
            _attach_pin_fit(result, payload, executable, easy_boxes)
    else:
        result.failure_reasons.append("no_coordinate" if attempted else "ocr_not_attempted")

    result.place_names = _place_names_from_text(detected_text)
    if not result.landmarks_detected:  # a pin fit may already have set these
        result.landmarks_detected = list(result.place_names)
    result.distress_terms = _distress_terms_from_text(detected_text)

    result.image_kind = classify_image_kind(
        payload,
        easyocr_box_count=len(easy_boxes),
        has_pin=result.pin_detected,
        has_coordinate=coordinate is not None,
    )

    # Placeholder confidence (real model in a later PR): printed / consensus
    # reads are trusted; a disputed read never is.
    family = result.coordinate_method_family
    result.coordinate_confidence = {
        "printed_text": 0.9,
        "ocr_consensus": 0.85,
        "ocr_single_engine": 0.5,
        "pin_landmark": 0.4,
        "ocr_disputed": 0.1,
        "none": 0.0,
    }[family]
    result.confidence_components = {"method_family": result.coordinate_confidence}

    if context_places:
        overlap = sorted(set(context_places) & set(result.place_names))
        result.diagnostics["context_place_overlap"] = overlap
    return result


def extract_from_url(
    url: str, *, context_places: tuple[str, ...] = ()
) -> ImageExtractionResult:
    payload = x_media_utils._download_bounded_image(url)
    if payload is None:
        result = ImageExtractionResult()
        result.failure_reasons.append("download_failed_or_disallowed")
        return result
    return extract_from_bytes(payload, context_places=context_places)
