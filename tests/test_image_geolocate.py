# SPDX-License-Identifier: AGPL-3.0-or-later
"""core.intel.image_geolocate -- Web-Mercator landmark fit (docs/prompt.md §7)."""
from __future__ import annotations

import math

from core.intel.image_geolocate import Landmark, _inv_merc, _merc, solve_pin_position

from tests.fixtures.alarm_phone_images import _LANDMARKS, _MAP_VIEWPORT


def _haversine_km(a, b):
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _landmarks(names):
    out = []
    for name in names:
        lat, lon = _LANDMARKS[name]
        px, py = _MAP_VIEWPORT.to_pixel(lat, lon)
        out.append(Landmark(name.lower(), float(px), float(py), lat, lon))
    return out


def test_mercator_round_trips():
    for lat, lon in [(35.0, 12.0), (41.5, 26.5), (34.27, 11.94)]:
        back = _inv_merc(*_merc(lat, lon))
        assert abs(back[0] - lat) < 1e-6 and abs(back[1] - lon) < 1e-6


def test_recovers_the_pin_from_three_landmarks():
    pin_latlon = (35.02, 12.18)
    pin_px = tuple(float(v) for v in _MAP_VIEWPORT.to_pixel(*pin_latlon))
    solution = solve_pin_position(
        pin_px,
        _landmarks(["Lampedusa", "Malta", "Pozzallo"]),
        image_size=(_MAP_VIEWPORT.width, _MAP_VIEWPORT.height),
    )
    assert solution is not None
    error_km = _haversine_km((solution.lat, solution.lon), pin_latlon)
    assert error_km < 5.0, f"{error_km:.1f} km off"
    assert solution.fit_residual_px < 3.0
    assert set(solution.landmarks_used) == {"lampedusa", "malta", "pozzallo"}
    assert solution.estimated_position_error_m > 0


def test_returns_none_below_two_landmarks():
    assert (
        solve_pin_position(
            (100.0, 100.0), _landmarks(["Lampedusa"]), image_size=(960, 720)
        )
        is None
    )


def test_ransac_drops_a_misplaced_label():
    pin_latlon = (35.02, 12.18)
    pin_px = tuple(float(v) for v in _MAP_VIEWPORT.to_pixel(*pin_latlon))
    good = _landmarks(["Lampedusa", "Linosa", "Malta", "Pozzallo"])
    # a fifth label whose pixel position is 200 px away from where its
    # coordinates say it should be (a wrong-instance OCR match)
    bad = Landmark("lampione", good[0].px + 220, good[0].py - 190, *_LANDMARKS["Lampione"])
    solution = solve_pin_position(
        pin_px, good + [bad], image_size=(_MAP_VIEWPORT.width, _MAP_VIEWPORT.height)
    )
    assert solution is not None
    assert "lampione" not in solution.landmarks_used
    assert _haversine_km((solution.lat, solution.lon), pin_latlon) < 6.0


def test_extrapolation_widens_the_error_estimate():
    inside = (35.6, 13.0)   # within the label hull
    far = (33.0, 12.3)      # well south of every label
    image_size = (_MAP_VIEWPORT.width, _MAP_VIEWPORT.height)
    marks = _landmarks(["Lampedusa", "Linosa", "Malta", "Pozzallo"])
    near = solve_pin_position(
        tuple(float(v) for v in _MAP_VIEWPORT.to_pixel(*inside)), marks, image_size=image_size
    )
    outside = solve_pin_position(
        tuple(float(v) for v in _MAP_VIEWPORT.to_pixel(*far)), marks, image_size=image_size
    )
    assert near is not None and outside is not None
    assert outside.max_extrapolation_px > near.max_extrapolation_px
    assert outside.estimated_position_error_m > near.estimated_position_error_m


def test_linear_degree_fit_would_be_worse_far_from_labels():
    """The bias a linear lat/lon fit introduces vs the Mercator fit, over a
    viewport spanning ~3 deg of latitude, is real -- prove the Mercator fit
    stays accurate where the linear one drifts."""
    pin_latlon = (34.30, 12.0)
    image_size = (_MAP_VIEWPORT.width, _MAP_VIEWPORT.height)
    marks = _landmarks(["Lampedusa", "Linosa", "Malta", "Pozzallo"])
    merc_solution = solve_pin_position(
        tuple(float(v) for v in _MAP_VIEWPORT.to_pixel(*pin_latlon)),
        marks,
        image_size=image_size,
    )
    assert merc_solution is not None
    merc_err = _haversine_km((merc_solution.lat, merc_solution.lon), pin_latlon)

    # linear-in-degrees inverse fit (the old approach)
    pin_px = _MAP_VIEWPORT.to_pixel(*pin_latlon)
    xs = [m.px for m in marks]
    ys = [m.py for m in marks]
    lons = [m.lon for m in marks]
    lats = [m.lat for m in marks]

    def _fit(ind, dep):
        n = len(ind)
        mx = sum(ind) / n
        my = sum(dep) / n
        sxx = sum((v - mx) ** 2 for v in ind)
        sxy = sum((a - mx) * (b - my) for a, b in zip(ind, dep))
        slope = sxy / sxx
        return slope, my - slope * mx

    sx, ix = _fit(lons, xs)
    sy, iy = _fit(lats, ys)
    lin_lon = (pin_px[0] - ix) / sx
    lin_lat = (pin_px[1] - iy) / sy
    lin_err = _haversine_km((lin_lat, lin_lon), pin_latlon)

    assert merc_err < 3.0
    assert merc_err <= lin_err
