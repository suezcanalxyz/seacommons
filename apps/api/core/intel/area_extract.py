# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a sea-only search-area polygon for reports with no precise position.

Every location this system plots is a boat -- always at sea, never on land.
A bare place-name match ("informed authorities in Italy and Malta") gives no
single defensible point: rather than picking whichever place matches first
and drawing an arbitrary circle around it, this follows what the report
actually names -- a single place becomes a circle around it, multiple named
places become the sea corridor between them -- clipped to water only, then
optionally narrowed further using real wave-height data if (and only if)
the report itself claims rough weather.

Uses:
  - core.intel.landmask (roaring_landmask) to clip out land, already an
    installed OpenDrift dependency.
  - core.ocean.cmems (already used for drift simulation) for wave height,
    when the report mentions weather.
  - shapely (already installed) only for hull/buffer geometry on an
    already-computed grid of lat/lon points -- never for the km-accurate
    grid generation itself, which stays in the same haversine/equirectangular
    approximation already used throughout this package (geoextract.py,
    map_pin_geolocate.py) rather than mixing in a second, subtly different
    notion of distance.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.intel import landmask
from core.intel.geoextract import find_all_place_matches, mentions_severe_weather

logger = logging.getLogger(__name__)

# Same "rough seas" threshold already used for SAR-conditions alerts
# elsewhere in this codebase (core.anomaly.weather._SAR_WAVE_M) -- one
# definition of "rough" across the system, not a second guess at it.
_SEA_STATE_WAVE_M = 2.5

_GRID_SPACING_KM = 8.0
_MAX_GRID_POINTS = 900
_SINGLE_PLACE_RADIUS_KM = {"imprecise": 120.0, "precise": 25.0}
_CORRIDOR_HALF_WIDTH_KM = 45.0
# Above this, a polygon isn't a usable search hint anymore -- it must say so
# rather than imply a confidence the data doesn't support.
_LOW_CONFIDENCE_AREA_KM2 = 6000.0


@dataclass
class AreaResult:
    polygon: dict  # GeoJSON Polygon, {"type": "Polygon", "coordinates": [...]}
    centroid: tuple[float, float]  # (lat, lon)
    confidence: str  # "area" | "area_low_confidence"
    weather_narrowed: bool


def extract_area(text: str, *, report_time: Optional[datetime] = None) -> Optional[AreaResult]:
    """None if no place is named at all, or if land/geometry construction
    fails outright -- callers fall back to their existing single-point
    behavior in that case, never to a fabricated area."""
    matches = find_all_place_matches(text)
    if not matches:
        return None

    points = [coords for _name, coords, _tier in matches]
    tiers = [tier for _name, _coords, tier in matches]
    radius_km = _SINGLE_PLACE_RADIUS_KM["imprecise" if "imprecise" in tiers else "precise"]

    # Most gazetteer seed points are already coastal-ish, but a handful
    # (a country's own geographic centroid, not its coastline) can sit far
    # enough inland that the base radius never reaches open water at all
    # (found and fixed for Libya/Somalia specifically -- this is the
    # general-case safety net for any other entry not individually audited).
    sea_grid: list[tuple[float, float]] = []
    for attempt_radius in (radius_km, radius_km * 2):
        grid = _build_base_grid(points, attempt_radius)
        sea_grid = [p for p in grid if landmask.is_on_land(*p) is not True]
        if sea_grid:
            break
    if not sea_grid:
        # Either the landmask is unavailable, or genuinely no sea point was
        # found nearby even after expanding the search -- no honest area to
        # report.
        return None

    narrowed = False
    working_grid = sea_grid
    if mentions_severe_weather(text):
        rough = _filter_by_wave_height(sea_grid, report_time)
        if rough:
            working_grid = rough
            narrowed = True
        # else: weather data didn't confirm anything unusual anywhere in
        # the base area (or CMEMS was unavailable) -- keep the full sea
        # area rather than silently narrowing to nothing.

    polygon = _cells_to_polygon(working_grid, _GRID_SPACING_KM)
    if polygon is None:
        return None

    area_km2 = _polygon_area_km2(polygon)
    confidence = "area" if (narrowed or area_km2 <= _LOW_CONFIDENCE_AREA_KM2) else "area_low_confidence"
    return AreaResult(
        polygon=polygon,
        centroid=_polygon_centroid(polygon),
        confidence=confidence,
        weather_narrowed=narrowed,
    )


# ── Grid construction (haversine/equirectangular, consistent with the rest
#    of core.intel) ──────────────────────────────────────────────────────


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _dist_to_segment_km(
    lat: float, lon: float, a: tuple[float, float], b: tuple[float, float],
) -> float:
    """Local equirectangular projection, fine at Mediterranean scale."""
    origin_lat = a[0]
    lon_scale = max(0.2, math.cos(math.radians(origin_lat)))

    def to_xy(lat_: float, lon_: float) -> tuple[float, float]:
        return (lon_ * 111.32 * lon_scale, lat_ * 111.32)

    px, py = to_xy(lat, lon)
    ax, ay = to_xy(*a)
    bx, by = to_xy(*b)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    proj_x, proj_y = ax + t * dx, ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _build_base_grid(
    points: list[tuple[float, float]],
    radius_km: float,
    spacing_km: float = _GRID_SPACING_KM,
    max_points: int = _MAX_GRID_POINTS,
) -> list[tuple[float, float]]:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    avg_lat = sum(lats) / len(lats)
    lon_scale = max(0.2, math.cos(math.radians(avg_lat)))
    pad_lat = radius_km / 111.32
    pad_lon = radius_km / (111.32 * lon_scale)
    lat_min, lat_max = min(lats) - pad_lat, max(lats) + pad_lat
    lon_min, lon_max = min(lons) - pad_lon, max(lons) + pad_lon

    step_deg = spacing_km / 111.32
    n_lat = max(1, int((lat_max - lat_min) / step_deg))
    n_lon = max(1, int((lon_max - lon_min) / step_deg))
    while (n_lat + 1) * (n_lon + 1) > max_points:
        spacing_km *= 1.3
        step_deg = spacing_km / 111.32
        n_lat = max(1, int((lat_max - lat_min) / step_deg))
        n_lon = max(1, int((lon_max - lon_min) / step_deg))

    grid: list[tuple[float, float]] = []
    for i in range(n_lat + 1):
        lat = lat_min + i * step_deg
        for j in range(n_lon + 1):
            lon = lon_min + j * step_deg
            if len(points) == 1:
                if _haversine_km(lat, lon, *points[0]) <= radius_km:
                    grid.append((lat, lon))
            else:
                near_any = any(
                    _dist_to_segment_km(lat, lon, points[k], points[k + 1]) <= _CORRIDOR_HALF_WIDTH_KM
                    for k in range(len(points) - 1)
                )
                if near_any:
                    grid.append((lat, lon))
    return grid


def _filter_by_wave_height(
    points: list[tuple[float, float]], report_time: Optional[datetime],
) -> list[tuple[float, float]]:
    from core.ocean.cmems import cmems_enabled, fetch_ocean_batch

    if not cmems_enabled():
        return []
    try:
        results = fetch_ocean_batch(points, at=report_time)
    except Exception as exc:
        logger.warning("area_extract: CMEMS batch fetch failed: %s", exc)
        return []
    return [
        pt for pt, r in zip(points, results)
        if r is not None and (r.get("wave_height_m") or 0.0) > _SEA_STATE_WAVE_M
    ]


# ── Geometry assembly (shapely, only on an already-computed point set) ────


def _cells_to_polygon(points: list[tuple[float, float]], spacing_km: float) -> Optional[dict]:
    if not points:
        return None
    from shapely.geometry import MultiPoint, mapping

    avg_lat = sum(lat for lat, _lon in points) / len(points)
    lon_scale = max(0.2, math.cos(math.radians(avg_lat)))
    buffer_deg = (spacing_km / 2) / (111.32 * lon_scale)

    coords_xy = [(lon, lat) for lat, lon in points]
    hull = MultiPoint(coords_xy).convex_hull.buffer(buffer_deg)
    return mapping(hull)


def _polygon_area_km2(polygon_geojson: dict) -> float:
    from shapely.geometry import shape

    geom = shape(polygon_geojson)
    lon_scale = max(0.2, math.cos(math.radians(geom.centroid.y)))
    deg2_to_km2 = (111.32 ** 2) * lon_scale
    return geom.area * deg2_to_km2


def _polygon_centroid(polygon_geojson: dict) -> tuple[float, float]:
    from shapely.geometry import shape

    c = shape(polygon_geojson).centroid
    return (c.y, c.x)
