# SPDX-License-Identifier: AGPL-3.0-or-later
"""Traceable confidence for an image-derived coordinate (docs/prompt.md §5).

`image_extraction` used a single per-method-family constant (printed = 0.9,
consensus = 0.85, disputed = 0.1 ...). That hides *why* a coordinate is
trusted and gives the same number to a clean printed readout inside the
operational region and to one that parsed a stray number pair from the map
furniture.

This module scores the six named components the prompt asks for and combines
them. `region_validity` is a hard multiplier: a coordinate outside the
operational envelope scores 0 and the caller drops it (fail closed -- a wrong
coordinate is worse than none).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from core.intel.landmask import in_operational_region

# A coordinate-looking OCR span: has a digit and a degree / minute / hemisphere
# mark or a decimal degree.
_COORD_HINT = re.compile(r"\d.*[°'\"°′″NSEWnsew]|\d+\.\d{3,}")

_PARSER_VALIDITY = {
    "printed_text": 1.0,
    "ocr_consensus": 0.9,
    "ocr_single_engine": 0.6,
    "pin_landmark": 0.5,     # replaced by the solver confidence when known
    "ocr_disputed": 0.15,
    "none": 0.0,
}

# interengine distance at/under which the two engines are "agreeing".
_ENGINE_AGREE_M = 250.0
_ENGINE_DISAGREE_M = 2000.0

_WEIGHTS = {
    "parser_validity": 0.35,
    "engine_agreement": 0.30,
    "ocr_confidence": 0.15,
    "landmask_validity": 0.12,
    "context_agreement": 0.08,
}

# A read the method itself already declared untrustworthy is never rescued by
# the softer components -- the two engines disagree (disputed), or there is no
# coordinate at all.
_FAMILY_CEILING = {
    "ocr_disputed": 0.12,
    "none": 0.0,
}


@dataclass(frozen=True)
class ConfidenceComponents:
    parser_validity: float = 0.0
    engine_agreement: float = 0.5
    ocr_confidence: float = 0.5
    region_validity: float = 0.0
    context_agreement: float = 0.5
    landmask_validity: float = 0.6

    def as_dict(self) -> dict[str, float]:
        return {k: round(v, 3) for k, v in asdict(self).items()}

    def score(self) -> float:
        base = sum(_WEIGHTS[name] * getattr(self, name) for name in _WEIGHTS)
        return round(max(0.0, min(1.0, self.region_validity * base)), 3)


def _engine_agreement(method_family: str, interengine_distance_m: float | None) -> float:
    if method_family == "ocr_disputed":
        return 0.1
    if method_family == "ocr_consensus":
        if interengine_distance_m is None:
            return 0.8
        if interengine_distance_m <= _ENGINE_AGREE_M:
            return 1.0
        if interengine_distance_m >= _ENGINE_DISAGREE_M:
            return 0.2
        span = _ENGINE_DISAGREE_M - _ENGINE_AGREE_M
        return round(1.0 - 0.8 * (interengine_distance_m - _ENGINE_AGREE_M) / span, 3)
    if method_family == "printed_text":
        return 0.6      # single-engine printed readout, no cross-check needed
    return 0.5          # single engine / pin -- unknown, neutral


def _ocr_confidence(easy_boxes: list[dict]) -> float:
    hits = [
        conf
        for box in easy_boxes
        if _COORD_HINT.search(str(box.get("text", "")))
        and (conf := float(box.get("confidence", 0.0) or 0.0)) > 0.0
    ]
    if not hits:
        return 0.5  # no per-box confidence to go on -- neutral, not a penalty
    return round(max(0.0, min(1.0, sum(hits) / len(hits))), 3)


def _region_validity(lat: float | None, lon: float | None) -> float:
    if lat is None or lon is None:
        return 0.0
    return 1.0 if in_operational_region(lat, lon) else 0.0


def _context_agreement(context_overlap: list[str] | None) -> float:
    # docs/prompt.md §8: caption place names *validate* an image coordinate,
    # they never move it. Overlap is a bounded bonus; absence is not a penalty.
    return 0.9 if context_overlap else 0.5


def combined_confidence(components: ConfidenceComponents, method_family: str) -> float:
    """The single 0..1 confidence: component score under the family ceiling."""
    return round(min(components.score(), _FAMILY_CEILING.get(method_family, 1.0)), 3)


def score_coordinate(
    method_family: str,
    *,
    lat: float | None,
    lon: float | None,
    interengine_distance_m: float | None = None,
    easy_boxes: list[dict] | None = None,
    context_overlap: list[str] | None = None,
    pin_solver_confidence: float | None = None,
    landmask_validity: float = 0.6,
) -> ConfidenceComponents:
    parser_validity = _PARSER_VALIDITY.get(method_family, 0.0)
    if method_family == "pin_landmark" and pin_solver_confidence is not None:
        parser_validity = round(max(0.05, min(1.0, pin_solver_confidence)), 3)
    return ConfidenceComponents(
        parser_validity=parser_validity,
        engine_agreement=_engine_agreement(method_family, interengine_distance_m),
        ocr_confidence=_ocr_confidence(easy_boxes or []),
        region_validity=_region_validity(lat, lon),
        context_agreement=_context_agreement(context_overlap),
        landmask_validity=landmask_validity,
    )
