# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md F-04 / F-05 / Phase 1.1 -- one shared location-evidence model.

OCR-method semantics must be identical for live ingestion and backfill, and a
disputed / unverified coordinate must never *supersede* a verified one.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.intel.location_evidence import (
    LocationEvidence,
    evidence_from_ocr_method,
    land_sea_class_for,
    location_evidence_id,
    location_quality,
    location_status_for,
    method_for,
    metadata_quality,
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


def test_any_real_ocr_read_outranks_a_region_fallback():
    region = location_quality("region_area", None)
    centroid = location_quality("place_centroid", None)
    unverified_ocr = location_quality("media_ocr_text", "machine_ocr_unverified", 1500)
    pin = location_quality("media_pin_landmark", "machine_ocr_unverified", 4000)
    assert region == centroid
    assert region < pin < unverified_ocr


def test_metadata_quality_reads_the_event_metadata_keys():
    verified = metadata_quality({
        "coordinate_source": "media_ocr_consensus",
        "coordinate_review_status": "machine_ocr_consensus_verified",
        "location_uncertainty_m": 400,
    })
    disputed = metadata_quality({
        "coordinate_source": "media_ocr_text",
        "coordinate_review_status": "machine_ocr_disputed_needs_review",
    })
    assert disputed < verified


def test_ocr_result_label():
    assert ocr_result_label("easyocr_tesseract_consensus") == "consensus"
    assert ocr_result_label("easyocr_text_disputed") == "disputed"
    assert ocr_result_label("tesseract_text") == "text_unverified"
    assert ocr_result_label("pin_landmark") == "pin_landmark"


# ── docs/fixes.md M3: schema additions ──────────────────────────────────────

def test_method_maps_coordinate_source_to_the_m3_vocabulary():
    assert method_for("post_text") == "text_reported"
    assert method_for("navtext") == "text_reported"
    assert method_for("media_ocr_text") == "ocr"
    assert method_for("media_ocr_consensus") == "ocr"
    assert method_for("media_pin_landmark") == "pin_fit"
    assert method_for("region_area") == "region_fallback"
    assert method_for("place_centroid") == "region_fallback"
    assert method_for("relative_place_offset") == "region_fallback"


def test_method_is_none_for_a_source_outside_the_m3_vocabulary():
    """AIS/GFW/VIIRS/ACLED geometries aren't extracted via any of the six
    M3 methods -- honestly unmapped rather than forced into a wrong bucket."""
    assert method_for("ais_position") is None
    assert method_for("gfw") is None
    assert method_for(None) is None


def test_location_evidence_method_property_reads_its_own_coordinate_source():
    evidence = LocationEvidence(coordinate_source="media_ocr_consensus")
    assert evidence.method == "ocr"


def test_location_evidence_id_is_deterministic_per_source_and_method():
    first = location_evidence_id("obs:abc123", "ocr")
    second = location_evidence_id("obs:abc123", "ocr")
    different_method = location_evidence_id("obs:abc123", "text_reported")
    assert first == second
    assert first != different_method


def test_land_sea_class_is_unknown_without_a_coordinate():
    assert land_sea_class_for(None, None) == "unknown"


def test_land_sea_class_is_unknown_when_the_landmask_is_unavailable():
    """Matches the autouse test-suite default (landmask off, see
    conftest._landmask_off) -- 'unknown' is not a guess."""
    assert land_sea_class_for(35.5, 14.1) == "unknown"


def test_land_sea_class_reflects_the_landmask_when_available(monkeypatch):
    monkeypatch.setattr("core.intel.landmask.is_on_land", lambda lat, lon: True)
    assert land_sea_class_for(35.5, 14.1) == "land"
    monkeypatch.setattr("core.intel.landmask.is_on_land", lambda lat, lon: False)
    assert land_sea_class_for(35.5, 14.1) == "sea"


# ── docs/fixes.md M3 exit gate: end-to-end location_status_for fixtures ────
# "end-to-end fixtures for point-at-sea, point-on-land, region-only,
# OCR-disputed and resolved incident."

def test_exit_gate_point_at_sea_is_positioned():
    status = location_status_for(
        lat=35.5, lon=14.1,
        coordinate_source="post_text",
        coordinate_review_status="not_required",
        is_land=False,
    )
    assert status == "positioned"


def test_exit_gate_point_on_land_is_withheld_from_maritime_map():
    status = location_status_for(
        lat=41.9, lon=12.5,  # Rome -- inland
        coordinate_source="post_text",
        coordinate_review_status="not_required",
        is_land=True,
    )
    assert status == "withheld_from_maritime_map"


def test_exit_gate_region_only_stays_region_only_never_fabricates_a_point():
    status = location_status_for(
        lat=None, lon=None,
        coordinate_source="region_area",
        coordinate_review_status=None,
        has_area_geometry=True,
        is_land=False,
    )
    assert status == "region_only"
    # A coarse centroid IS present (region_area's lat/lon is a centroid, not
    # a real point) -- still region_only, per "region-only cannot fabricate
    # a point" (docs/fixes.md M3 rules).
    centroid_status = location_status_for(
        lat=35.0, lon=14.0,
        coordinate_source="region_area",
        coordinate_review_status=None,
        is_land=False,
    )
    assert centroid_status == "region_only"


def test_exit_gate_ocr_disputed_is_disputed_not_positioned():
    status = location_status_for(
        lat=35.5, lon=14.1,
        coordinate_source="media_ocr_text",
        coordinate_review_status="machine_ocr_disputed_needs_review",
        is_land=False,
    )
    assert status == "disputed"


def test_exit_gate_a_resolved_incident_keeps_its_real_point():
    """docs/fixes.md M3 rule: 'a real point supersedes stale region-only
    geometry.' A humanitarian incident resolving does not itself degrade
    a real extracted point back to region-only or unpositioned -- lifecycle
    and location evidence are independent concerns that must still compose
    correctly."""
    from core.intel.lifecycle import distress_lifecycle
    from core.intel.store import IntelEvent

    now = datetime.now(timezone.utc)
    event = IntelEvent(
        text="Update: all 40 people were rescued and disembarked safely at the port of Lampedusa",
        lat=35.5,
        lon=14.1,
        timestamp_utc=(now - timedelta(hours=2)).isoformat(),
        metadata={"coordinate_source": "post_text", "coordinate_review_status": "not_required"},
    )
    assert distress_lifecycle(event, now=now, same_source=[event]) == "resolved"
    status = location_status_for(
        lat=event.lat, lon=event.lon,
        coordinate_source=event.metadata["coordinate_source"],
        coordinate_review_status=event.metadata["coordinate_review_status"],
        is_land=False,
    )
    assert status == "positioned"
