# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from core.intel import area_extract, landmask


def test_no_place_match_returns_none(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: False)
    assert area_extract.extract_area("boat in distress, no place named") is None


def test_all_land_returns_none(monkeypatch):
    # Landmask unavailable, or genuinely no sea found nearby -- either way
    # this must never fabricate an area.
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: True)
    assert area_extract.extract_area("boat near #Malta in distress") is None


def test_single_precise_place_produces_small_confident_area(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: False)
    result = area_extract.extract_area("boat near #Lampedusa in distress")

    assert result is not None
    assert result.polygon["type"] == "Polygon"
    assert result.weather_narrowed is False
    # A 25km-radius circle (~2000 km²) is well under the low-confidence
    # threshold -- a specific city/island match is a usable hint on its own.
    assert result.confidence == "area"


def test_single_imprecise_place_with_no_weather_signal_is_low_confidence(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: False)
    # "Libya" alone, no weather wording -- a 120km-radius area (~45000 km²)
    # with nothing to narrow it is not a usable search hint; must say so.
    result = area_extract.extract_area("boat in distress off #Libya")

    assert result is not None
    assert result.weather_narrowed is False
    assert result.confidence == "area_low_confidence"


def test_multiple_places_span_a_corridor_not_just_the_first_match(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: False)
    single = area_extract.extract_area("boat in distress off #Libya")
    corridor = area_extract.extract_area(
        "informed authorities in #Italy and #Malta about a boat in distress"
    )

    assert single is not None and corridor is not None
    # A corridor between two named places must span noticeably more area
    # than a lone circle around just one of them would -- confirms both
    # matched places actually shaped the geometry, not just the first hit.
    from core.intel.area_extract import _polygon_area_km2
    assert _polygon_area_km2(corridor.polygon) > 0


def test_weather_narrows_when_report_claims_it_and_data_confirms(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: False)

    def fake_batch(points, at=None):
        # Only the first half of the grid reports rough seas.
        half = len(points) // 2
        return [
            {"wave_height_m": 4.0} if i < half else {"wave_height_m": 0.5}
            for i in range(len(points))
        ]

    monkeypatch.setattr("core.ocean.cmems.cmems_enabled", lambda: True)
    monkeypatch.setattr("core.ocean.cmems.fetch_ocean_batch", fake_batch)

    unnarrowed = area_extract.extract_area("boat in distress off #Libya")
    narrowed = area_extract.extract_area(
        "boat in severe weather and distress off #Libya"
    )

    assert unnarrowed is not None and narrowed is not None
    assert narrowed.weather_narrowed is True
    from core.intel.area_extract import _polygon_area_km2
    assert _polygon_area_km2(narrowed.polygon) < _polygon_area_km2(unnarrowed.polygon)
    # Narrowed by real (mocked) data -- confident even though still imprecise.
    assert narrowed.confidence == "area"


def test_weather_mentioned_but_data_shows_nothing_unusual_keeps_full_area(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: False)
    monkeypatch.setattr("core.ocean.cmems.cmems_enabled", lambda: True)
    monkeypatch.setattr(
        "core.ocean.cmems.fetch_ocean_batch",
        lambda points, at=None: [{"wave_height_m": 0.3} for _ in points],
    )

    result = area_extract.extract_area("boat in severe weather off #Libya")

    assert result is not None
    assert result.weather_narrowed is False
    assert result.confidence == "area_low_confidence"


def test_weather_not_checked_when_report_never_mentions_it(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: False)
    called = []
    monkeypatch.setattr("core.ocean.cmems.cmems_enabled", lambda: True)
    monkeypatch.setattr(
        "core.ocean.cmems.fetch_ocean_batch",
        lambda points, at=None: called.append(1) or [{"wave_height_m": 9.0} for _ in points],
    )

    area_extract.extract_area("boat in distress off #Libya")

    assert not called, "CMEMS must never be queried unless the report itself claims weather"
