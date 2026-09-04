# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from core.intel import landmask
from core.intel.geoextract import extract_coords


def test_already_at_sea_returns_unchanged(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: False)
    assert landmask.nearest_sea_point(35.9, 14.51) == (35.9, 14.51)


def test_unavailable_landmask_returns_unchanged(monkeypatch):
    # is_on_land itself never raises (it catches internally) — returns None
    # when the real library can't be loaded. Must be treated as "leave it".
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: None)
    assert landmask.nearest_sea_point(35.9, 14.51) == (35.9, 14.51)


def test_on_land_searches_outward_until_sea(monkeypatch):
    # Land only at the exact starting point; everywhere else is sea — the
    # very first ring/bearing tried must escape it.
    origin = (35.9, 14.51)
    calls = []

    def fake_is_on_land(lat, lon):
        calls.append((lat, lon))
        return (round(lat, 5), round(lon, 5)) == origin

    monkeypatch.setattr(landmask, "is_on_land", fake_is_on_land)
    result = landmask.nearest_sea_point(*origin)

    assert result != origin
    # First call must be the origin itself (the initial on-land check).
    assert calls[0] == origin
    # Result must actually be near the origin, not a distant fallback —
    # the first ring is 5km, so well under half a degree away.
    assert abs(result[0] - origin[0]) < 0.5
    assert abs(result[1] - origin[1]) < 0.5


def test_gives_up_and_keeps_original_when_land_never_ends(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: True)
    origin = (35.9, 14.51)
    assert landmask.nearest_sea_point(*origin, max_radius_km=15, step_km=5) == origin


def test_gazetteer_fallback_is_nudged_off_land(monkeypatch):
    # Real production case: "informed authorities in #Italy and #Malta"
    # resolves through the bare gazetteer branch to Malta's own centroid,
    # which sits on the island itself.
    # geoextract binds nearest_sea_point at import — patch it where it is used.
    monkeypatch.setattr(
        "core.intel.geoextract.nearest_sea_point", lambda lat, lon: (99.0, 99.0),
    )
    assert extract_coords("boat near #Malta in distress") == (99.0, 99.0)


# ── docs/fixes.md M4.2: distance_to_coast_km ────────────────────────────────

def test_distance_to_coast_is_zero_when_already_on_land(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: True)
    assert landmask.distance_to_coast_km(41.9, 12.5) == 0.0


def test_distance_to_coast_is_none_when_the_landmask_is_unavailable(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: None)
    assert landmask.distance_to_coast_km(35.5, 14.1) is None


def test_distance_to_coast_searches_outward_until_land(monkeypatch):
    # Land only far from the query point -- the search must expand rings
    # until it finds it, and report a distance in the right ballpark.
    origin = (35.5, 14.1)
    land_radius_km = 15.0

    def fake_is_on_land(lat, lon):
        if (round(lat, 5), round(lon, 5)) == origin:
            return False
        # Approximate: land classified once far enough from the origin.
        d_lat_km = (lat - origin[0]) * 111.32
        d_lon_km = (lon - origin[1]) * 111.32 * max(0.2, __import__("math").cos(__import__("math").radians(origin[0])))
        return (d_lat_km ** 2 + d_lon_km ** 2) ** 0.5 >= land_radius_km

    monkeypatch.setattr(landmask, "is_on_land", fake_is_on_land)
    result = landmask.distance_to_coast_km(*origin)
    assert result is not None
    assert 0.0 < result <= 30.0  # found within a couple of rings of the true radius


def test_distance_to_coast_gives_up_within_max_radius_over_open_ocean(monkeypatch):
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: False)
    assert landmask.distance_to_coast_km(35.5, 14.1, max_radius_km=15, step_km=5) is None


def test_mask_loading_is_lazy_not_at_import_time():
    # Every other test in this file mocks is_on_land directly, so the real
    # (slow, ~20-30s) landmask load is never actually triggered anywhere in
    # this suite — confirms _mask stays an inert, uncalled lru_cache until
    # something genuinely needs it.
    assert landmask._mask.cache_info().currsize == 0
