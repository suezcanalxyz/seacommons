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

        get_durable = get

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


def test_original_land_coordinate_is_rejected_even_if_snapping_finds_sea(monkeypatch):
    """Never seed a maritime model by moving a reported land origin offshore."""
    monkeypatch.setattr("core.intel.landmask.is_on_land", lambda *_: True)
    monkeypatch.setattr(
        "core.intel.landmask.nearest_sea_point",
        lambda *_: (_ for _ in ()).throw(AssertionError("must not snap origin")),
    )
    event = _distress(coordinate_source="post_text", coordinate_review_status="not_required")
    ok, reason = is_auto_drift_eligible(event)
    assert not ok and "land" in reason


def test_unavailable_landmask_fails_closed(monkeypatch):
    """An unknown land/sea classification is not proof of a sea origin."""
    monkeypatch.setattr("core.intel.landmask.is_on_land", lambda *_: None)
    event = _distress(coordinate_source="post_text", coordinate_review_status="not_required")
    ok, reason = is_auto_drift_eligible(event)
    assert not ok and "unverified" in reason


def test_landmask_exception_fails_closed(monkeypatch):
    def _broken(*_args):
        raise RuntimeError("coastline dataset unavailable")

    monkeypatch.setattr("core.intel.landmask.is_on_land", _broken)
    event = _distress(coordinate_source="post_text", coordinate_review_status="not_required")
    ok, reason = is_auto_drift_eligible(event)
    assert not ok and "unverified" in reason


def test_nonfinite_and_out_of_region_origins_cannot_seed_drift():
    for lat, lon in ((float("nan"), 11.94), (34.27, float("inf")), (91.0, 11.94)):
        event = _distress(coordinate_source="post_text", coordinate_review_status="not_required")
        event.lat, event.lon = lat, lon
        assert is_auto_drift_eligible(event)[0] is False


def test_invalid_location_uncertainty_cannot_seed_drift(monkeypatch):
    monkeypatch.setattr("core.intel.landmask.is_on_land", lambda *_: False)
    for uncertainty in (float("nan"), float("inf"), -1, "not-a-number"):
        event = _distress(
            coordinate_source="post_text",
            coordinate_review_status="not_required",
            location_uncertainty_m=uncertainty,
        )
        ok, reason = is_auto_drift_eligible(event)
        assert not ok and "uncertainty" in reason


def test_missing_durable_event_never_bypasses_origin_gate(monkeypatch):
    class _MissingStore:
        def get_durable(self, _event_id):
            return None

        def update_metadata(self, *_args, **_kwargs):
            raise AssertionError("unknown events must not be mutated")

    monkeypatch.setattr(ds, "intel_store", _MissingStore())
    monkeypatch.setattr(
        ds, "acquire_drift_slot",
        lambda: (_ for _ in ()).throw(AssertionError("missing event acquired a slot")),
    )
    for force in (False, True):
        assert schedule_intel_drift(
            "missing-event", 34.27, 11.94, None, "rubber_boat",
            "2026-11-01T12:00:00Z", force=force,
        ) is False


def test_scheduled_origin_must_match_verified_durable_coordinate(monkeypatch):
    event = _distress(
        coordinate_source="post_text", coordinate_review_status="not_required",
    )

    class _Store:
        def get_durable(self, _event_id):
            return event

        def update_metadata(self, _event_id, *, metadata):
            event.metadata.update(metadata)

    monkeypatch.setattr(ds, "intel_store", _Store())
    monkeypatch.setattr(ds, "is_auto_drift_eligible", lambda _event: (True, "eligible"))
    monkeypatch.setattr(
        ds, "acquire_drift_slot",
        lambda: (_ for _ in ()).throw(AssertionError("unverified origin acquired a slot")),
    )
    for lat, lon in (
        (35.27, 11.94),
        (34.27, 12.94),
        (float("nan"), 11.94),
        (34.27, "invalid"),
    ):
        assert schedule_intel_drift(
            event.id, lat, lon, None, "rubber_boat",
            "2026-11-01T12:00:00Z", force=True,
        ) is False


def test_scheduler_seeds_from_verified_durable_coordinate(monkeypatch):
    event = _distress(
        coordinate_source="post_text", coordinate_review_status="not_required",
    )
    calls = []

    class _Store:
        def get_durable(self, _event_id):
            return event

        def update_metadata(self, _event_id, *, metadata):
            event.metadata.update(metadata)

    monkeypatch.setattr(ds, "intel_store", _Store())
    monkeypatch.setattr(ds, "is_auto_drift_eligible", lambda _event: (True, "eligible"))
    monkeypatch.setattr(ds, "acquire_drift_slot", lambda: True)
    monkeypatch.setattr(ds, "_run_intel_drift", lambda *args: calls.append(args))
    assert schedule_intel_drift(
        event.id, event.lat + 0.0000001, event.lon, None, "rubber_boat",
        "2026-11-01T12:00:00Z", force=True, background=False,
    ) is True
    assert len(calls) == 1
    assert calls[0][1:3] == (event.lat, event.lon)


def test_metadata_only_verified_text_coordinate_can_seed_after_durable_double_check(monkeypatch):
    """Legacy verified text points must use the identical origin in both gates."""
    event = _distress(
        coordinate_source="post_text", coordinate_review_status="not_required",
        lat=34.27, lon=11.94, location_uncertainty_m=250,
    )
    event.lat, event.lon = None, None
    ok, reason = is_auto_drift_eligible(event)
    assert ok, reason
    calls = []

    class _Store:
        def get_durable(self, _event_id):
            return event

        def update_metadata(self, _event_id, *, metadata):
            event.metadata.update(metadata)

    monkeypatch.setattr(ds, "intel_store", _Store())
    monkeypatch.setattr(ds, "acquire_drift_slot", lambda: True)
    monkeypatch.setattr(ds, "_run_intel_drift", lambda *args: calls.append(args))
    assert schedule_intel_drift(
        event.id, 34.27, 11.94, None, "rubber_boat",
        "2026-11-02T20:00:00Z", force=True, background=False,
    ) is True
    assert len(calls) == 1
    assert calls[0][1:3] == (34.27, 11.94)


def test_metadata_only_region_centroid_remains_blocked(monkeypatch):
    event = _distress(
        coordinate_source="region_area", coordinate_review_status="not_required",
        lat=35.0, lon=15.0, location_uncertainty_m=60000,
    )
    event.lat, event.lon = None, None
    ok, reason = is_auto_drift_eligible(event)
    assert not ok

    class _Store:
        def get_durable(self, _event_id):
            return event

        def update_metadata(self, _event_id, *, metadata):
            event.metadata.update(metadata)

    monkeypatch.setattr(ds, "intel_store", _Store())
    monkeypatch.setattr(
        ds, "acquire_drift_slot",
        lambda: (_ for _ in ()).throw(AssertionError("region-only origin acquired a slot")),
    )
    assert schedule_intel_drift(
        event.id, 35.0, 15.0, None, "rubber_boat",
        "2026-11-02T20:00:00Z", force=True,
    ) is False
    assert event.metadata["drift_status"] == "ineligible"


def test_canonical_point_is_not_overridden_by_stale_metadata():
    """The durable reviewed point remains authoritative over legacy meta."""
    event = _distress(
        coordinate_source="post_text", coordinate_review_status="not_required",
        lat=40.0, lon=20.0,
    )
    ok, reason = is_auto_drift_eligible(event)
    assert ok, reason


def test_partial_canonical_coordinate_never_mixes_with_legacy_metadata():
    """A partially updated canonical fix cannot borrow the other axis."""
    for canonical_lat, canonical_lon in ((34.27, None), (None, 11.94)):
        event = _distress(
            coordinate_source="post_text",
            coordinate_review_status="not_required",
            lat=38.5, lon=17.5, location_uncertainty_m=250,
        )
        event.lat, event.lon = canonical_lat, canonical_lon
        assert ds.drift_origin_coordinates(event) == (canonical_lat, canonical_lon)
        ok, reason = is_auto_drift_eligible(event)
        assert not ok
        assert reason == "no coordinate to originate a drift"


def test_partial_canonical_origin_cannot_acquire_drift_slot(monkeypatch):
    """Even a forced scheduler call must fail before any model work."""
    event = _distress(
        coordinate_source="post_text",
        coordinate_review_status="not_required",
        lat=38.5, lon=17.5, location_uncertainty_m=250,
    )
    event.lat, event.lon = 34.27, None

    class _Store:
        def get_durable(self, _event_id):
            return event

        def update_metadata(self, _event_id, *, metadata):
            event.metadata.update(metadata)

    monkeypatch.setattr(ds, "intel_store", _Store())
    monkeypatch.setattr(
        ds, "acquire_drift_slot",
        lambda: (_ for _ in ()).throw(AssertionError("partial origin acquired model slot")),
    )
    assert schedule_intel_drift(
        event.id, 34.27, 17.5, None, "rubber_boat",
        "2026-11-02T21:00:00Z", force=True,
    ) is False
    assert event.metadata["drift_status"] == "ineligible"
    assert "no coordinate" in event.metadata["drift_ineligible_reason"]
