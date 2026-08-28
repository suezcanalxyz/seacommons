# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared geospatial primitives.

Small, dependency-free helpers used across the intel / fusion / anomaly code.
Historically each module carried its own private ``_haversine`` copy
(``core.intel.triangulation._haversine_km``,
``core.zones.classifier._haversine_nm``, plus copies in the AIS code); new
call sites should import from here instead.
"""

from __future__ import annotations

import math
from typing import Iterable, Protocol, Sequence

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in kilometres."""
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(max(0.0, a)))


def within_km(lat1: float, lon1: float, lat2: float, lon2: float, km: float) -> bool:
    """True when two points are at most ``km`` apart."""
    return haversine_km(lat1, lon1, lat2, lon2) <= km


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, degrees clockwise from north."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lon = math.radians(lon2 - lon1)
    y = math.sin(d_lon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def cluster_key(
    lat: float,
    lon: float,
    ts_epoch_s: float,
    *,
    precision_km: float = 15.0,
    window_s: float = 5400.0,
) -> str:
    """A stable coarse bucket id for one place+time.

    Two signals that fall in the same spatial cell (~``precision_km``) and the
    same time bucket (``window_s``) get the same key — used to dedup correlated
    alerts and to rate-limit notifications for one incident.
    """
    deg_per_km_lat = 1.0 / 110.574
    lat_step = max(precision_km * deg_per_km_lat, 1e-4)
    lat_cell = math.floor(lat / lat_step)
    # Derive the longitude step from the *quantised* latitude so two nearby
    # points always use the same step (a per-point cos(lat) makes the cell
    # boundary jitter and splits neighbours).
    band_lat = (lat_cell + 0.5) * lat_step
    cos_lat = max(math.cos(math.radians(band_lat)), 0.01)
    lon_step = max(precision_km * deg_per_km_lat / cos_lat, 1e-4)
    lon_cell = math.floor(lon / lon_step)
    time_cell = int(ts_epoch_s // max(window_s, 1.0))
    return f"{lat_cell}:{lon_cell}:{time_cell}"


class _HasPosition(Protocol):
    lat: float
    lon: float
    ts: float


def cluster(
    points: Sequence[_HasPosition],
    *,
    radius_km: float = 15.0,
    window_s: float = 5400.0,
) -> list[list[_HasPosition]]:
    """Greedy single-link spatiotemporal clustering.

    Each item must expose ``lat`` / ``lon`` / ``ts`` (epoch seconds). Two items
    are linked when they are within ``radius_km`` and ``window_s`` of each
    other; linked items (transitively) share a cluster. O(n^2) — fine for the
    few-hundred-event windows this is used on.
    """
    parent = list(range(len(points)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            a, b = points[i], points[j]
            if abs(a.ts - b.ts) > window_s:
                continue
            if within_km(a.lat, a.lon, b.lat, b.lon, radius_km):
                union(i, j)

    groups: dict[int, list[_HasPosition]] = {}
    for i, point in enumerate(points):
        groups.setdefault(find(i), []).append(point)
    return list(groups.values())


def centroid(points: Iterable[tuple[float, float]]) -> tuple[float, float] | None:
    """Arithmetic mean of (lat, lon) pairs — adequate at Mediterranean scale."""
    lats: list[float] = []
    lons: list[float] = []
    for lat, lon in points:
        lats.append(lat)
        lons.append(lon)
    if not lats:
        return None
    return sum(lats) / len(lats), sum(lons) / len(lons)
