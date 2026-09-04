# SPDX-License-Identifier: AGPL-3.0-or-later
"""One shared representation of an extracted location's evidence quality.

docs/fixes.md F-04 / F-05 / Phase 1.1: OCR-method-string -> (coordinate_source,
uncertainty, review_status) semantics were duplicated -- and had already
diverged -- between core.intel.twikit_monitor._apply_media_ocr (live) and
core.intel.backfill_alarm_phone.apply_position (historical). A disputed or
lone-engine coordinate could also outrank a verified one because upgrade
decisions compared source rank alone. This module is the single place both
concerns are defined.

docs/fixes.md M3 standardizes this dataclass with the fields the spec names
that were still missing: ``location_evidence_id``, ``source_observation_id``
(the link to the M1.1 durable SourceObservation row), ``engine_results``,
``consensus``, ``land_sea_class`` and ``algorithm_version``, plus optional
area-geometry fields for the region-only case. Purely additive -- every new
field defaults to ``None``/empty, so every existing construction call site
(twikit_monitor, backfill_alarm_phone, ...) keeps working unchanged. This
stays an in-memory value object, same as before M3; there is no persisted
``LocationEvidenceDB`` table yet.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from core.domain.live_contracts import CoordinateReviewStatus as _CRS

# docs/fixes.md M3's method vocabulary. Distinct from coordinate_source (the
# existing, much finer-grained vocabulary every call site already writes) --
# method() below is a read-only *view* of coordinate_source in these six
# buckets, not a replacement for it; renaming coordinate_source everywhere it
# is already stored/queried is out of scope here.
_METHOD_FOR_SOURCE: dict[str, str] = {
    "post_text": "text_reported",
    "post_text_or_maritime_place": "text_reported",
    "navtext": "text_reported",
    "media_ocr_text": "ocr",
    "media_ocr_consensus": "ocr",
    "media_pin_landmark": "pin_fit",
    "region_area": "region_fallback",
    "place_centroid": "region_fallback",
    "relative_place_offset": "region_fallback",
}


def method_for(coordinate_source: str | None) -> Optional[str]:
    """docs/fixes.md M3 ``method`` vocabulary for a coordinate_source value.

    Returns ``None`` for a source this mapping doesn't cover -- e.g. a
    structured-feed geometry (``ais_position``/``gfw``/``viirs``/``acled``)
    that isn't extracted via any of these six methods at all. ``operator``
    and ``landmark_fit`` currently have no coordinate_source callers ever
    write (no operator-entered-coordinate or landmark-fit-distinct-from-
    pin-fit path exists yet); both stay reachable values here for when one
    does, rather than being silently unmappable forever.
    """
    return _METHOD_FOR_SOURCE.get(str(coordinate_source or "").lower())


def location_evidence_id(source_observation_id: str, method: str) -> str:
    """Deterministic id, same (source_observation_id, method) always
    resolves to the same id -- mirrors
    core.intel.source_observation.observation_id's construction."""
    digest = hashlib.blake2s(
        f"{source_observation_id}:{method}".encode(), digest_size=16,
    ).hexdigest()
    return f"loc:{digest}"


def land_sea_class_for(lat: float | None, lon: float | None) -> str:
    """"sea" | "land" | "unknown" -- the M3 land_sea_class field, built on
    the same landmask core.intel.landmask.is_on_land already uses
    everywhere else. "unknown" (not a guess) when there's no coordinate or
    the landmask itself is unavailable."""
    if lat is None or lon is None:
        return "unknown"
    from core.intel.landmask import is_on_land

    on_land = is_on_land(lat, lon)
    if on_land is None:
        return "unknown"
    return "land" if on_land else "sea"


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
    # docs/fixes.md M3 additions -- see module docstring. (The field below
    # and the module-level location_evidence_id() function are independent
    # namespaces -- an instance's `.location_evidence_id` attribute access
    # never shadows the function.)
    location_evidence_id: Optional[str] = None
    source_observation_id: Optional[str] = None
    engine_results: list[dict[str, Any]] = field(default_factory=list)
    consensus: Optional[bool] = None
    land_sea_class: Optional[str] = None
    algorithm_version: Optional[str] = None
    area_geojson: Optional[dict[str, Any]] = None
    area_radius_m: Optional[float] = None

    @property
    def method(self) -> Optional[str]:
        """docs/fixes.md M3 method vocabulary -- see method_for()."""
        return method_for(self.coordinate_source)

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

    def quality(self) -> tuple[int, float]:
        return location_quality(
            self.coordinate_source, self.review_status, self.uncertainty_m
        )


# ── OCR method -> evidence semantics (the one definition) ─────────────────────
_OCR_METHOD_EVIDENCE: dict[str, tuple[str, float, str, bool]] = {
    "easyocr_tesseract_consensus": (
        "media_ocr_consensus", 400.0, _CRS.MACHINE_OCR_CONSENSUS_VERIFIED.value, False,
    ),
    "easyocr_text_disputed": (
        "media_ocr_text", 3500.0, _CRS.MACHINE_OCR_DISPUTED_NEEDS_REVIEW.value, True,
    ),
}
_OCR_TEXT_FALLBACK = ("media_ocr_text", 1500.0, _CRS.MACHINE_OCR_UNVERIFIED.value, True)
_OCR_PIN_FALLBACK = ("media_pin_landmark", 4000.0, _CRS.MACHINE_OCR_UNVERIFIED.value, True)


def evidence_from_ocr_method(
    method: str,
    lat: float | None,
    lon: float | None,
    *,
    engine: str | None = None,
    estimated_position_error_m: float | None = None,
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
    if estimated_position_error_m is not None:
        try:
            uncertainty = max(uncertainty, float(estimated_position_error_m))
        except (TypeError, ValueError):
            pass
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
# One ordered ladder, high to low:
#   human_verified / reported_exact  (9)
#   coordinate read from post text / navtext / AIS   (8)
#   EasyOCR + Tesseract consensus    (6)
#   lone-engine OCR text read        (5)
#   OCR engines disagree (disputed)  (4)
#   map-pin landmark estimate        (3)
#   relative place offset            (2)
#   place centroid / region area     (1)
#   nothing                          (0)
# A disputed / lone-engine coordinate can be stored for review but never
# *supersedes* a verified one.
_SOURCE_ONLY_RANK: dict[str, int] = {
    "": 0,
    "none": 0,
    "place_centroid": 1,
    "region_area": 1,
    "relative_place_offset": 2,
    "media_pin_landmark": 3,
    "media_ocr_text": 5,
    "media_ocr_consensus": 6,
    "navtext": 8,
    "ais_position": 8,
    "post_text": 8,
}


# A "coarse" coordinate source only knows a region, not a position: its
# lat/lon is a centroid, so a named-area search polygon (when one exists) is
# the better public geometry. Every other source is a real extracted point.
COARSE_COORDINATE_SOURCES = frozenset(
    {"", "none", "region_area", "place_centroid", "relative_place_offset"}
)
_COARSE_SOURCES = COARSE_COORDINATE_SOURCES


def _evidence_rank(source: str, review: str) -> int:
    if review in (_CRS.HUMAN_VERIFIED.value, _CRS.REPORTED_EXACT.value):
        return 9
    if review == _CRS.NOT_REQUIRED.value:
        # "no OCR review needed" means text coordinates -- never a coarse
        # place/region fallback that some legacy rows also tagged this way.
        return _SOURCE_ONLY_RANK.get(source, 4) if source in _COARSE_SOURCES else 8
    if review == _CRS.MACHINE_OCR_CONSENSUS_VERIFIED.value:
        return 6
    if review == _CRS.MACHINE_OCR_UNVERIFIED.value:
        return 3 if source == "media_pin_landmark" else 5
    if "disputed" in review or "needs_review" in review:
        return 4
    # No / unknown review status -> rank on the source's inherent coarseness.
    return _SOURCE_ONLY_RANK.get(source, 4)


def location_quality(
    coordinate_source: str | None,
    review_status: str | None,
    uncertainty_m: float | None = None,
) -> tuple[int, float]:
    """A sortable quality key -- higher is better evidence.

    ``(evidence rank, tighter uncertainty)``. The rank is the single ladder
    above; a tighter uncertainty only breaks ties within the same rank.
    """
    source = str(coordinate_source or "none").lower()
    review = str(review_status or "").lower()
    rank = _evidence_rank(source, review)
    try:
        neg_uncertainty = -float(uncertainty_m) if uncertainty_m is not None else -1e12
    except (TypeError, ValueError):
        neg_uncertainty = -1e12
    return (rank, neg_uncertainty)


def metadata_quality(meta: Mapping[str, Any] | None) -> tuple[int, float]:
    """location_quality() read from an IntelEvent.metadata mapping."""
    meta = meta or {}
    return location_quality(
        meta.get("coordinate_source"),
        meta.get("coordinate_review_status"),
        meta.get("location_uncertainty_m"),
    )


# ── Canonical review-status / location-status derivation ─────────────────────
_COARSE_COORD_SOURCES = frozenset(
    {"", "none", "region_area", "place_centroid", "relative_place_offset"}
)


def canonical_review_status(coordinate_source: str | None, stored: str | None) -> str | None:
    """The coordinate_review_status a row *should* carry.

    A coarse place/region fallback tagged ``not_required`` (which means "text
    coordinates, no OCR review") is corrected to ``not_applicable`` -- the
    same fix live ingestion applies (docs/fixes.md F-04, twikit_monitor).
    """
    source = str(coordinate_source or "").lower()
    review = str(stored or "").lower()
    if source in _COARSE_COORD_SOURCES:
        if review in ("", _CRS.NOT_REQUIRED.value):
            return _CRS.NOT_APPLICABLE.value
    return stored or None


def location_status_for(
    *,
    lat: float | None,
    lon: float | None,
    coordinate_source: str | None,
    coordinate_review_status: str | None,
    has_area_geometry: bool = False,
    is_land: bool = False,
) -> str:
    """The one LocationStatus computer (docs/fixes.md Question D).

    positioned | region_only | disputed | withheld_from_maritime_map |
    unpositioned
    """
    review = str(coordinate_review_status or "").lower()
    source = str(coordinate_source or "").lower()
    if is_land:
        return "withheld_from_maritime_map"
    if "disputed" in review or "needs_review" in review:
        return "disputed"
    # A real extracted point (OCR text/consensus, pin-landmark fit, coordinate
    # read from the post) is `positioned` even if a now-stale area_geojson is
    # still attached -- the polygon was only the pre-extraction fallback. Same
    # rule the public geometry projection uses (core.intel.public_geometry).
    if lat is not None and lon is not None and source not in COARSE_COORDINATE_SOURCES:
        return "positioned"
    if has_area_geometry or source == "region_area":
        return "region_only"
    if lat is None or lon is None:
        return "unpositioned"
    if source in ("place_centroid", "relative_place_offset", "", "none"):
        return "region_only"
    return "positioned"
