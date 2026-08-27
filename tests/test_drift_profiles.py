# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 15a: per-object-class drift model selection."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.drift.profiles import DEFAULT_PROFILE, resolve_profile


def test_sar_objects_stay_on_leeway_with_their_object_type() -> None:
    assert resolve_profile(vessel_type="rubber_boat").model == "leeway"
    assert resolve_profile(vessel_type="rubber_boat").leeway_object_type == 38
    assert resolve_profile(vessel_type="person_in_water").leeway_object_type == 26
    assert resolve_profile(vessel_type="life_raft", persons=3).leeway_object_type == 27
    assert resolve_profile(vessel_type="life_raft", persons=8).leeway_object_type == 29


def test_large_and_powered_hulls_use_oceandrift_not_piw_leeway() -> None:
    for vessel_type in ("container_ship", "cargo", "tanker", "motorboat", "sailboat"):
        profile = resolve_profile(vessel_type=vessel_type)
        assert profile.model == "oceandrift", vessel_type
        assert profile.leeway_object_type is None, vessel_type
        assert profile.wind_drift_factor is not None and profile.wind_drift_factor < 0.05

    # A tanker has the lowest windage of the set.
    assert resolve_profile(vessel_type="tanker").wind_drift_factor < resolve_profile(
        vessel_type="container_ship"
    ).wind_drift_factor


def test_case_type_supplies_a_default_when_no_vessel_type() -> None:
    assert resolve_profile(case_type="missing_persons").object_class == "person_in_water"
    assert resolve_profile(case_type="vessel_incident").model == "oceandrift"
    assert resolve_profile(case_type="pushback").object_class == "rubber_boat"


def test_shipwreck_is_a_multi_object_debris_field() -> None:
    profile = resolve_profile(case_type="shipwreck")
    assert profile.object_class == "shipwreck_debris_field"
    assert profile.model == "leeway"
    assert profile.debris_mix is not None
    object_types = [ot for ot, _ in profile.debris_mix]
    assert 26 in object_types  # person in water
    assert sum(fraction for _, fraction in profile.debris_mix) == pytest.approx(1.0)


def test_vessel_type_wins_over_case_type() -> None:
    profile = resolve_profile(vessel_type="tanker", case_type="distress_sar")
    assert profile.object_class == "tanker"


def test_unknown_input_falls_back_to_the_conservative_sar_default() -> None:
    assert resolve_profile() is DEFAULT_PROFILE
    assert resolve_profile(vessel_type="teleporter").object_class == "rubber_boat"
    assert resolve_profile(case_type="not_a_case_type").object_class == "rubber_boat"


def test_engine_opendrift_payload_selects_the_model(monkeypatch) -> None:
    from core.drift import engine as engine_module

    captured: dict = {}

    def fake_run_leeway(payload):
        captured.update(payload)
        return {
            "trajectory": {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[14.0, 35.0], [14.1, 35.1]]},
                "properties": {"timestamps_utc": ["a", "b"], "speed_ms": [0.1, 0.2]},
            },
            "cone_6h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[]]}, "properties": {}},
            "cone_12h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[]]}, "properties": {}},
            "cone_24h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[]]}, "properties": {}},
            "impact_point": {"type": "FeatureCollection", "features": []},
            "metadata": {"model": "OpenDrift OceanDrift"},
        }

    monkeypatch.setattr(engine_module, "run_leeway", fake_run_leeway)
    monkeypatch.setattr(engine_module.CacheManager, "get_wind_live", lambda self, a, b: {"wind_speed_ms": 5.0, "wind_dir_deg": 270.0})
    monkeypatch.setattr(engine_module.CacheManager, "get_ocean_currents", lambda self, a, b: {"u_ms": 0.1, "v_ms": 0.0})
    monkeypatch.setattr(engine_module.CacheManager, "get_wind_forecast_series", lambda self, a, b, hours=48: [])
    monkeypatch.setattr(engine_module.runtime_config, "DEMO_PUBLIC_MODE", False)

    eng = engine_module.DriftEngine()
    eng.compute(35.0, 14.0, datetime(2026, 7, 28, tzinfo=timezone.utc), duration_h=12,
                config={"vessel_type": "container_ship"})

    assert captured["model"] == "oceandrift"
    assert captured["object_class"] == "cargo_container_ship"
    assert captured["wind_drift_factor"] == pytest.approx(0.015)
    assert captured["object_type"] == 26  # unused by oceandrift, kept for payload shape


def test_intel_drift_seeds_the_ensemble_over_the_report_position_uncertainty(monkeypatch) -> None:
    from core.intel import drift_service
    from core.intel.store import IntelEvent, intel_store

    event = IntelEvent(
        id="unc-evt-1", type="twitter", severity="high", title="Boat in the Malta SAR zone",
        source="alarm_phone", lat=35.9, lon=14.5,
        metadata={"location_uncertainty_m": 25_000, "coordinate_source": "region_area"},
    )
    intel_store.add(event)

    captured: dict = {}

    class _FakeEngine:
        def compute(self, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop after capture")

    import core.db.store as store_module
    import core.drift.engine as engine_module

    monkeypatch.setattr(engine_module, "DriftEngine", _FakeEngine)
    monkeypatch.setattr(store_module, "create_drift_job", lambda *a, **k: None)
    monkeypatch.setattr(store_module, "fail_drift_job", lambda *a, **k: None)

    drift_service._run_intel_drift_inner(
        "unc-evt-1", 35.9, 14.5, None, "rubber_boat", "2026-08-21T16:00:00+00:00"
    )

    assert captured["config"]["seed_radius_m"] == 25_000.0  # not the fixed 150 m


def test_intel_drift_seed_radius_is_capped(monkeypatch) -> None:
    from core.intel import drift_service
    from core.intel.store import IntelEvent, intel_store

    intel_store.add(IntelEvent(
        id="unc-evt-2", type="twitter", severity="high", title="Somewhere in the Med",
        source="alarm_phone", lat=35.0, lon=16.0,
        metadata={"location_uncertainty_m": 500_000},
    ))
    captured: dict = {}

    class _FakeEngine:
        def compute(self, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop")

    import core.db.store as store_module
    import core.drift.engine as engine_module

    monkeypatch.setattr(engine_module, "DriftEngine", _FakeEngine)
    monkeypatch.setattr(store_module, "create_drift_job", lambda *a, **k: None)
    monkeypatch.setattr(store_module, "fail_drift_job", lambda *a, **k: None)

    drift_service._run_intel_drift_inner(
        "unc-evt-2", 35.0, 16.0, None, "rubber_boat", "2026-08-21T16:00:00+00:00"
    )
    assert captured["config"]["seed_radius_m"] == 50_000.0  # capped
