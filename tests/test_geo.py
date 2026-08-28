# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared geospatial helpers."""
from __future__ import annotations

from dataclasses import dataclass

from core.geo import cluster, cluster_key, haversine_km, within_km


def test_haversine_known_distance() -> None:
    # Lampedusa → Malta is ~178 km great-circle.
    d = haversine_km(35.50, 12.60, 35.90, 14.51)
    assert 160 < d < 195
    # a degree of latitude is ~111 km everywhere
    assert 108 < haversine_km(35.0, 13.0, 36.0, 13.0) < 114


def test_within_km() -> None:
    assert within_km(35.0, 13.0, 35.05, 13.05, 10)
    assert not within_km(35.0, 13.0, 36.0, 14.0, 10)


def test_cluster_key_buckets_nearby_and_contemporaneous() -> None:
    a = cluster_key(35.000, 13.000, 1_000_000)
    b = cluster_key(35.002, 13.002, 1_000_500)
    far = cluster_key(38.0, 20.0, 1_000_000)
    later = cluster_key(35.0, 13.0, 1_000_000 + 20_000)
    assert a == b
    assert a != far
    assert a != later


@dataclass
class _P:
    lat: float
    lon: float
    ts: float


def test_cluster_single_link() -> None:
    points = [
        _P(35.0, 13.0, 0),
        _P(35.05, 13.05, 600),      # links to the first
        _P(41.0, 20.0, 0),          # isolated
    ]
    groups = cluster(points, radius_km=15, window_s=3600)
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2]
