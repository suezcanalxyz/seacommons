from __future__ import annotations

from datetime import datetime, timezone


def test_current_cache_separates_historical_times(monkeypatch, tmp_path):
    import core.drift.cache as cache_mod

    calls = []
    def fake_current(lat, lon, *, at=None):
        calls.append(at)
        return {"current_speed_ms": 1.0, "current_dir_deg": 90.0, "source": "cmems-test"}

    monkeypatch.setattr(cache_mod, "fetch_current_point", fake_current)
    manager = cache_mod.CacheManager(cache_dir=tmp_path)
    first = manager.get_ocean_currents(35.0, 14.0, "2026-10-20T10:00:00+00:00")
    repeat = manager.get_ocean_currents(35.0, 14.0, "2026-10-20T10:00:00+00:00")
    second = manager.get_ocean_currents(35.0, 14.0, "2026-10-21T10:00:00+00:00")

    assert first == repeat
    assert first["u_ms"] == 1.0
    assert second["u_ms"] == 1.0
    assert len(calls) == 2
    assert calls[0].date().isoformat() == "2026-10-20"
    assert calls[1].date().isoformat() == "2026-10-21"
    names = {path.name for path in tmp_path.glob("currents_*.json")}
    assert any("20261020T10" in name for name in names)
    assert any("20261021T10" in name for name in names)


def test_invalid_forcing_time_fails_closed_without_provider_call(monkeypatch, tmp_path):
    import core.drift.cache as cache_mod

    monkeypatch.setattr(
        cache_mod,
        "fetch_current_point",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider must not run")),
    )
    result = cache_mod.CacheManager(cache_dir=tmp_path).get_ocean_currents(35.0, 14.0, "not-a-time")
    assert result == {"u_ms": 0.0, "v_ms": 0.0, "source": "invalid-time-fallback"}


def test_drift_engine_passes_case_timestamp_to_current_cache(monkeypatch):
    import core.drift.engine as engine_mod

    requested = []
    class FakeCache:
        def get_wind_live(self, lat, lon):
            return {"wind_speed_ms": 5.0, "wind_dir_deg": 270.0, "source": "test"}
        def get_ocean_currents(self, lat, lon, time_utc=None):
            requested.append(time_utc)
            return {"u_ms": 0.1, "v_ms": 0.2, "source": "test"}
        def get_wind_forecast_series(self, lat, lon, hours=48):
            return []

    fake_result = {
        "trajectory": {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[14.0, 35.0], [14.1, 35.1]]}, "properties": {}},
        "cone_6h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {}},
        "cone_12h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {}},
        "cone_24h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {}},
        "impact_point": None,
        "metadata": {},
    }
    monkeypatch.setattr(engine_mod, "run_leeway", lambda payload: fake_result)
    engine = engine_mod.DriftEngine()
    engine._cache = FakeCache()
    at = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
    engine.compute(35.0, 14.0, at, duration_h=6, config={"persons": 1})
    assert requested == [at.isoformat()]


def test_historical_drift_does_not_use_live_wind(monkeypatch):
    import core.drift.engine as engine_mod

    captured = {}
    class FakeCache:
        def get_wind_live(self, *args, **kwargs):
            raise AssertionError("historical drift must not fetch live wind")
        def get_wind_forecast_series(self, *args, **kwargs):
            raise AssertionError("historical drift must not fetch live forecast")
        def get_ocean_currents(self, lat, lon, time_utc=None):
            return {"u_ms": 0.0, "v_ms": 0.0, "source": "unavailable-fallback"}

    def fake_run(payload):
        captured.update(payload)
        return {
            "trajectory": {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[14, 35], [14.1, 35.1]]}, "properties": {}},
            "cone_6h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {}},
            "cone_12h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {}},
            "cone_24h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {}},
            "impact_point": None,
            "metadata": {},
        }

    monkeypatch.setattr(engine_mod, "run_leeway", fake_run)
    engine = engine_mod.DriftEngine()
    engine._cache = FakeCache()
    engine.compute(35.0, 14.0, datetime(2026, 10, 20, tzinfo=timezone.utc), duration_h=6)
    assert captured["environment"]["x_wind"] == 0.0
    assert captured["environment"]["y_wind"] == 0.0
    assert captured["wind_series"] == []


def test_backtrack_does_not_fetch_unrelated_live_wind(monkeypatch):
    import core.drift.engine as engine_mod

    engine = engine_mod.DriftEngine()
    class NoLiveWind:
        def get_wind_live(self, *args, **kwargs):
            raise AssertionError('backtrack must not fetch current wind')
    engine._cache = NoLiveWind()
    captured = {}
    def fake_opendrift(lat, lon, at, duration_h, domain, cfg):
        captured.update(cfg)
        return object()
    monkeypatch.setattr(engine, '_opendrift', fake_opendrift)
    engine.backtrack(35.0, 14.0, datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert captured['x_wind'] < 0
    assert captured['x_sea_water_velocity'] < 0
