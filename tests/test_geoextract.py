# SPDX-License-Identifier: AGPL-3.0-or-later
"""Coordinate extraction: region gating and sea-snapping.

Every coordinate this module returns is a boat position — it must be inside
the area SeaCommons covers and in the water.
"""
from __future__ import annotations

from core.intel.geoextract import (
    extract_coords,
    extract_numeric_coords,
    extract_relative_coords,
)


def test_numeric_coords_outside_the_region_are_rejected() -> None:
    # Real prod case: a text-only tweet about AlarmPhone activists in
    # Cote d'Ivoire yielded "-7, 44" (the Indian Ocean).
    assert extract_numeric_coords("meeting in Abidjan on -7, 44 next week") is None
    # Mid-Atlantic and the Gulf are out too.
    assert extract_numeric_coords("Position 15.0N 40.0W") is None


def test_numeric_coords_inside_the_region_pass() -> None:
    assert extract_numeric_coords("Position: 35.10N 013.50E") == (35.1, 13.5)
    # Canary Islands / Atlantic route stays in.
    lat, lon = extract_numeric_coords("N 28° 30' / W 015° 00'")
    assert abs(lat - 28.5) < 0.01 and abs(lon + 15.0) < 0.01


def test_extract_coords_sea_snaps_a_numeric_readout(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.intel.landmask.is_on_land",
        lambda lat, lon: abs(lat - 35.5) < 0.05 and abs(lon - 12.6) < 0.05,
    )
    result = extract_coords("boat in distress at 35.50N 12.60E")
    assert result is not None
    lat, lon = result
    assert not (abs(lat - 35.5) < 0.05 and abs(lon - 12.6) < 0.05)  # moved off Lampedusa


def test_relative_offset_is_sea_snapped(monkeypatch) -> None:
    # "20 km south of Crete" can land the computed point back on the island.
    seen: list[tuple[float, float]] = []

    def fake_is_on_land(lat: float, lon: float) -> bool:
        seen.append((lat, lon))
        return len(seen) == 1  # origin is "land", the first ring hit is "sea"

    monkeypatch.setattr("core.intel.landmask.is_on_land", fake_is_on_land)
    result = extract_relative_coords("rubber boat 20 km south of Crete")
    assert result is not None
    assert len(seen) >= 2  # a snap search ran
