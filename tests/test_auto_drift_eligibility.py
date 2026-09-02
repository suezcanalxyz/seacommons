# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md F-01 / Phase 0.1 -- one auto-drift evidence gate.

A SAR drift model must never originate from disputed, unverified or
non-maritime location evidence, and `force=True` (an OCR-upgrade recompute or
a refresher re-run) may bypass the once-only dedup guard but never this
policy.
"""
from __future__ import annotations

import core.intel.drift_service as ds
from core.intel.drift_service import is_auto_drift_eligible, schedule_intel_drift
from core.intel.store import IntelEvent


def _distress(**meta) -> IntelEvent:
    base = {"is_distress": True}
    base.update(meta)
    return IntelEvent(
        id="elig-" + str(abs(hash(frozenset(meta.items()))))[:8],
        type="twitter",
        severity="high",
        lat=34.27,
        lon=11.94,
        title="Boat in distress south of Lampedusa",
        text="",
        source="alarm_phone",
        metadata=base,
    )


def test_verified_text_coordinate_is_eligible():
    ok, reason = is_auto_drift_eligible(
        _distress(coordinate_source="post_text", coordinate_review_status="not_required")
    )
    assert ok, reason


def test_ocr_consensus_is_eligible():
    ok, reason = is_auto_drift_eligible(
        _distress(
            coordinate_source="media_ocr_consensus",
            coordinate_review_status="machine_ocr_consensus_verified",
            location_uncertainty_m=400,
        )
    )
    assert ok, reason


def test_disputed_ocr_is_rejected():
    ok, reason = is_auto_drift_eligible(
        _distress(
            coordinate_source="media_ocr_text",
            coordinate_review_status="machine_ocr_disputed_needs_review",
        )
    )
    assert not ok and "disputed" in reason


def test_single_engine_ocr_coordinate_at_sea_is_eligible():
    # Policy /2 (operator decision): an Alarm Phone distress map coordinate
    # that OCR read and that lands in the sea is a drift origin even from one
    # engine -- weaker evidence, wide radius, still a real position.
    ok, reason = is_auto_drift_eligible(
        _distress(
            coordinate_source="media_ocr_text",
            coordinate_review_status="machine_ocr_unverified",
            location_uncertainty_m=1500,
        )
    )
    assert ok, reason


def test_pin_landmark_estimate_at_sea_is_eligible():
    ok, reason = is_auto_drift_eligible(
        _distress(
            coordinate_source="media_pin_landmark",
            coordinate_review_status="machine_ocr_unverified",
            location_uncertainty_m=4000,
        )
    )
    assert ok, reason


def test_ocr_coordinate_on_land_is_rejected(monkeypatch):
    # The "coordinate in the sea" gate: an OCR'd coordinate that resolves to
    # land (an Evros / land-border Alarm Phone case) is never a drift origin,
    # whatever its OCR provenance.
    monkeypatch.setattr("core.intel.landmask.nearest_sea_point", lambda lat, lon: (lat, lon))
    monkeypatch.setattr("core.intel.landmask.is_on_land", lambda lat, lon: True)
    ok, reason = is_auto_drift_eligible(
        _distress(
            coordinate_source="media_ocr_text",
            coordinate_review_status="machine_ocr_unverified",
            location_uncertainty_m=1500,
        )
    )
    assert not ok and "land" in reason


def test_region_only_position_is_rejected():
    ok, reason = is_auto_drift_eligible(
        _distress(coordinate_source="region_area", location_uncertainty_m=25000)
    )
    assert not ok


def test_land_humanitarian_event_is_rejected():
    ok, reason = is_auto_drift_eligible(
        _distress(
            coordinate_source="post_text",
            coordinate_review_status="not_required",
            sea_land_class="LAND",
        )
    )
    assert not ok and "sea_land_class" in reason


def test_resolved_incident_is_rejected():
    event = _distress(coordinate_source="post_text", coordinate_review_status="not_required")
    event.text = "Update: all 40 people were rescued and are safe."
    ok, reason = is_auto_drift_eligible(event)
    assert not ok and "lifecycle" in reason


def test_maritime_security_domain_is_rejected():
    event = IntelEvent(
        id="elig-sec",
        type="ais_anomaly",
        severity="high",
        lat=35.0,
        lon=14.0,
        title="AIS spoofing",
        metadata={"anomaly_type": "sanctioned_vessel", "coordinate_source": "ais_position"},
    )
    ok, reason = is_auto_drift_eligible(event)
    assert not ok and "maritime_domain" in reason


def test_excessive_uncertainty_is_rejected():
    ok, reason = is_auto_drift_eligible(
        _distress(
            coordinate_source="post_text",
            coordinate_review_status="not_required",
            location_uncertainty_m=42000,
        )
    )
    assert not ok and "uncertainty" in reason


def test_force_cannot_bypass_the_evidence_gate(monkeypatch):
    """`force=True` may re-run a completed drift, but a disputed coordinate
    must still yield zero scheduling."""
    event = _distress(
        coordinate_source="media_ocr_text",
        coordinate_review_status="machine_ocr_disputed_needs_review",
        drift_status="completed",
    )

    class _Store:
        def get(self, _id):
            return event

        def update_metadata(self, _id, *, metadata):
            event.metadata.update(metadata)

    monkeypatch.setattr(ds, "intel_store", _Store())
    monkeypatch.setattr(
        ds,
        "acquire_drift_slot",
        lambda: (_ for _ in ()).throw(AssertionError("slot must not be acquired")),
    )

    assert schedule_intel_drift(event.id, 34.27, 11.94, None, "rubber_boat",
                                "2026-08-21T03:31:00Z", force=True) is False
    assert event.metadata["drift_status"] == "ineligible"
