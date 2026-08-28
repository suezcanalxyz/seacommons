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


def test_mask_loading_is_lazy_not_at_import_time():
    # Every other test in this file mocks is_on_land directly, so the real
    # (slow, ~20-30s) landmask load is never actually triggered anywhere in
    # this suite — confirms _mask stays an inert, uncalled lru_cache until
    # something genuinely needs it.
    assert landmask._mask.cache_info().currsize == 0
