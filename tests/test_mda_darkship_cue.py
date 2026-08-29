# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drift-cued dark-ship search geometry."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.mda.darkship_cue import build, reachable_polygon


def test_reachable_polygon_grows_with_time():
    small = reachable_polygon(35.0, 18.0, 90.0, 12.0, hours=1.0)
    big = reachable_polygon(35.0, 18.0, 90.0, 12.0, hours=6.0)
    assert big["_radius_km"] > small["_radius_km"] * 3
    assert small["coordinates"][0][0] == small["coordinates"][0][-1]   # closed ring


def test_reachable_polygon_biased_forward():
    poly = reachable_polygon(35.0, 18.0, 90.0, 15.0, hours=4.0)  # heading east
    ring = poly["coordinates"][0]
    east = max(c[0] for c in ring) - 18.0
    west = 18.0 - min(c[0] for c in ring)
    assert east > west   # extends further east (forward) than west (aft)


def test_build_offline_still_returns_area_and_estimate():
    cue = build(lat=34.5, lon=13.0, course_deg=270.0, speed_kn=10.0,
                gap_start=datetime.now(timezone.utc) - timedelta(hours=3))
    assert cue["dark_for_hours"] == 3.0
    assert cue["search_area"]["type"] == "Polygon"
    assert cue["next_s1_pass_estimate_hours"] >= 0
    assert "Sentinel-1" in cue["recommendation"] or "SAR" in cue["recommendation"]
