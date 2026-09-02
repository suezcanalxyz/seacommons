from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from core.ocean import cmems


class _Selection:
    def __init__(self, value: float):
        self.values = value


class _Variable:
    dims = ("depth", "time", "latitude", "longitude")
    coords: ClassVar[dict] = {"latitude": (), "longitude": ()}

    def __init__(self, value: float):
        self._value = value

    def isel(self, _selection):
        return self

    def sel(self, _selection, method=None):
        if "time" in _selection or "valid_time" in _selection:
            return self
        return _Selection(self._value)


class _Dataset(dict):
    coords: ClassVar[dict] = {"latitude": (), "longitude": ()}
    dims: ClassVar[dict] = {"latitude": (), "longitude": ()}


class _FakeCopernicus:
    def __init__(self):
        self.calls: list[dict] = []

    def open_dataset(self, **kwargs):
        self.calls.append(kwargs)
        values = {"uo": 0.1, "vo": 0.2, "thetao": 18.0, "VHM0": 1.5}
        return _Dataset({name: _Variable(values[name]) for name in kwargs["variables"]})


def test_ocean_batch_requests_the_dataset_surface_level_not_zero(monkeypatch):
    """Changing the depth request back to zero must reproduce the CMEMS warning."""
    fake = _FakeCopernicus()
    monkeypatch.setattr(cmems, "cmems_enabled", lambda: True)
    monkeypatch.setattr(cmems, "_load_copernicusmarine", lambda: fake)

    result = cmems.fetch_ocean_batch(
        [(35.0, 14.0)], at=datetime(2026, 9, 2, tzinfo=timezone.utc)
    )

    assert result[0] is not None
    depth_calls = [call for call in fake.calls if "minimum_depth" in call]
    assert len(depth_calls) == 2
    assert all(call["minimum_depth"] == 0.49402499198913574 for call in depth_calls)
    assert all(call["maximum_depth"] >= call["minimum_depth"] for call in depth_calls)


def test_current_point_requests_the_same_surface_level(monkeypatch):
    fake = _FakeCopernicus()
    monkeypatch.setattr(cmems, "cmems_enabled", lambda: True)
    monkeypatch.setattr(cmems, "_load_copernicusmarine", lambda: fake)

    result = cmems.fetch_current_point(35.0, 14.0)

    assert result is not None
    assert fake.calls[0]["minimum_depth"] == 0.49402499198913574
