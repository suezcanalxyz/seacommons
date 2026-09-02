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
    vessel_conditions: list[dict[str, Any]] = field(default_factory=list)
    needs: list[dict[str, Any]] = field(default_factory=list)
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
            }
            | (
                {"estimated_position_error_m": self.estimated_position_error_m}
                if self.estimated_position_error_m is not None
                else {}
            ),
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
            **({"image_people_counts": self.people_counts[:12]} if self.people_counts else {}),
            **({"image_vessel_conditions": self.vessel_conditions[:8]} if self.vessel_conditions else {}),
            **({"image_needs": self.needs[:8]} if self.needs else {}),
            "selected_method": self.coordinate_method,
            "selected_method_family": self.coordinate_method_family,
            "coordinate_confidence": self.coordinate_confidence,
            "coordinate_confidence_components": self.confidence_components,
            "image_place_names": self.place_names[:12],
            **(
                {"estimated_position_error_m": self.estimated_position_error_m}
                if self.estimated_position_error_m is not None
                else {}
            ),
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


def _text_fields_from_text(text: str) -> tuple[list[dict], list[dict], list[dict]]:
    """People / vessel-condition / needs candidates from OCR text (§9)."""
    from core.intel.image_text_fields import (
        extract_needs,
        extract_people,
        extract_vessel_conditions,
    )

    return (
        [span.as_dict() for span in extract_people(text)],
        [f.as_dict() for f in extract_vessel_conditions(text)],
        [f.as_dict() for f in extract_needs(text)],
    )


def _attach_pin_candidates(result, payload) -> None:
    """Record every ranked pin candidate (docs/prompt.md §6) for diagnostics,
    independent of whether a landmark fit later succeeds."""
    try:
        from PIL import Image, ImageOps

        from core.intel.image_pin import detect_pins, select_pin

        with Image.open(io.BytesIO(payload)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        candidates = detect_pins(image)
    except Exception:
        return
    result.pin_candidates = [c.as_dict() for c in candidates[:6]]
    if select_pin(candidates) is not None:
        result.pin_detected = True


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
    result.diagnostics["pin_solver_confidence"] = solution.confidence
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

    _attach_pin_candidates(result, payload)

    result.place_names = _place_names_from_text(detected_text)
    if not result.landmarks_detected:  # a pin fit may already have set these
        result.landmarks_detected = list(result.place_names)
    result.distress_terms = _distress_terms_from_text(detected_text)
    result.people_counts, result.vessel_conditions, result.needs = _text_fields_from_text(
        detected_text
    )

    result.image_kind = classify_image_kind(
        payload,
        easyocr_box_count=len(easy_boxes),
        has_pin=result.pin_detected,
        has_coordinate=coordinate is not None,
    )

    context_overlap = (
        sorted(set(context_places) & set(result.place_names)) if context_places else []
    )
    # docs/prompt.md §8: the caption's place names only *validate* the image
    # coordinate -- proximity is a bounded bonus, distance a bounded penalty.
    # The coordinate itself is never moved toward the caption centroid.
    context_proximity_km: Optional[float] = None
    if context_places and result.selected_coordinate is not None:
        from core.intel.geoextract import find_all_place_matches
        from core.intel.x_media_utils import haversine_m

        centroids = [c for _n, c, _t in find_all_place_matches(" ".join(context_places))]
        if centroids:
            context_proximity_km = round(
                min(
                    haversine_m(result.selected_coordinate, centroid) / 1000.0
                    for centroid in centroids
                ),
                1,
            )
    if context_places:
        result.diagnostics["context_place_overlap"] = context_overlap
        if context_proximity_km is not None:
            result.diagnostics["context_proximity_km"] = context_proximity_km

    # Traceable confidence (docs/prompt.md §5): six named components combined,
    # with region_validity as a hard multiplier.
    from core.intel.image_confidence import combined_confidence, score_coordinate

    lat = result.selected_coordinate[0] if result.selected_coordinate else None
    lon = result.selected_coordinate[1] if result.selected_coordinate else None
    components = score_coordinate(
        result.coordinate_method_family,
        lat=lat,
        lon=lon,
        interengine_distance_m=result.diagnostics.get("interengine_distance_m"),
        easy_boxes=easy_boxes,
        context_overlap=context_overlap,
        context_proximity_km=context_proximity_km,
        has_context=bool(context_places),
        pin_solver_confidence=result.diagnostics.get("pin_solver_confidence"),
    )
    result.confidence_components = components.as_dict()
    result.coordinate_confidence = combined_confidence(components, result.coordinate_method_family)

    # Fail closed: a coordinate outside the operational envelope is a bad
    # extraction (stray number pair, OCR misread, wrong landmark). A wrong
    # coordinate is worse than none -- drop it and keep the fallback the
    # caller already had (docs/prompt.md §5 / §13, audit invariant 4).
    if result.selected_coordinate is not None and components.region_validity == 0.0:
        result.failure_reasons.append("coordinate_out_of_operational_region")
        result.selected_coordinate = None
        result.coordinate_candidates = []
        result.coordinate_method = "none"
        result.coordinate_method_family = "none"

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
