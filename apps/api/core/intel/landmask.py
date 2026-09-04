# SPDX-License-Identifier: AGPL-3.0-or-later
"""Nudge a coordinate off land onto the nearest sea point.

Every location this system plots is a boat — always at sea. A gazetteer
centroid or a drop-pin reading can still legitimately land on a landmass
(a small island's true geometric center, a coastal city itself) even
though the report it came from is unambiguously offshore — e.g. "informed
authorities in Italy and Malta" resolving to Malta's own on-island
centroid. Rather than hand-curating an offshore offset per place name
forever (the approach used for Sfax/Crete before this module existed),
search outward from the raw point until landing on water.

Uses OpenDrift's own landmask backend (roaring_landmask — already an
installed dependency for drift simulation, so this adds nothing new).
Loading it is slow (~20-30s: a large embedded global coastline dataset),
so it is lazy and cached at module level — the cost is paid once per
process, on first actual use, never at import time. This module must stay
cheap to import for every service, including ones that never call it, and
for the test suite.
"""
from __future__ import annotations

import functools
import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

_COMPASS_STEPS = 16  # bearings tried at each radius ring
_RADIUS_STEP_KM = 5.0
_MAX_RADIUS_KM = 80.0

# Every distress location this system plots is a boat in the Mediterranean, the
# Black Sea, the Aegean, or the eastern-Atlantic migration routes (Gibraltar,
# Western Sahara / Canary Islands). A coordinate outside this generous envelope
# is a bad extraction (a stray number pair parsed out of tweet text, an OCR
# misread, a gazetteer miss) — plotting it as a "distress" pin somewhere in the
# Indian Ocean or mid-Atlantic is worse than showing nothing.
_REGION_LAT = (26.0, 48.0)
_REGION_LON = (-18.0, 43.0)


def in_operational_region(lat: float, lon: float) -> bool:
    """True if (lat, lon) is inside the maritime area SeaCommons covers.

    Pure arithmetic — no landmask load — so it is safe to call from the
    low-memory edge publisher on every event.
    """
    try:
        return (
            _REGION_LAT[0] <= float(lat) <= _REGION_LAT[1]
            and _REGION_LON[0] <= float(lon) <= _REGION_LON[1]
        )
    except (TypeError, ValueError):
        return False


@functools.lru_cache(maxsize=1)
def _mask():
    from roaring_landmask import RoaringLandmask

    logger.info("landmask: loading global coastline dataset (one-time, ~20-30s)...")
    return RoaringLandmask.new().mask


def is_on_land(lat: float, lon: float) -> Optional[bool]:
    """True/False, or None if the landmask can't be loaded — never raises,
    so a caller can always treat None the same as "unknown, leave it alone"."""
    try:
        return bool(_mask().contains(lon, lat))
    except Exception as exc:
        logger.warning("landmask: unavailable (%s) — skipping land check", exc)
        return None


def nearest_sea_point(
    lat: float,
    lon: float,
    *,
    max_radius_km: float = _MAX_RADIUS_KM,
    step_km: float = _RADIUS_STEP_KM,
) -> tuple[float, float]:
    """(lat, lon) unchanged if already at sea (or the landmask is
    unavailable); otherwise the nearest point found on a radial search
    that isn't on land, searched ring by ring outward from the origin.
    """
    if is_on_land(lat, lon) is not True:
        return (lat, lon)

    radius = step_km
    while radius <= max_radius_km:
        for i in range(_COMPASS_STEPS):
            bearing = math.radians(360.0 * i / _COMPASS_STEPS)
            north_km = math.cos(bearing) * radius
            east_km = math.sin(bearing) * radius
            candidate_lat = lat + north_km / 111.32
            lon_scale = max(0.2, math.cos(math.radians(lat)))
            candidate_lon = lon + east_km / (111.32 * lon_scale)
            if is_on_land(candidate_lat, candidate_lon) is False:
                return (round(candidate_lat, 5), round(candidate_lon, 5))
        radius += step_km

    logger.warning(
        "landmask: no sea point found within %skm of (%s, %s); keeping the original",
        max_radius_km, lat, lon,
    )
    return (lat, lon)


def distance_to_coast_km(
    lat: float,
    lon: float,
    *,
    max_radius_km: float = _MAX_RADIUS_KM,
    step_km: float = _RADIUS_STEP_KM,
) -> Optional[float]:
    """docs/fixes.md M4.2 coverage-baseline field. Approximate distance from
    a sea point to the nearest land, via the same ring-by-ring radial
    search nearest_sea_point() already does in the opposite direction (sea
    from land here; land from sea there) -- same compass-step/radius-step
    parameters, same tolerance.

    Returns ``0.0`` if the point is already on land, ``None`` if the
    landmask is unavailable or nothing land-classified is found within
    ``max_radius_km`` (open ocean far from any coast this system's
    operational region would ever plot).
    """
    on_land = is_on_land(lat, lon)
    if on_land is None:
        return None
    if on_land:
        return 0.0

    radius = step_km
    while radius <= max_radius_km:
        for i in range(_COMPASS_STEPS):
            bearing = math.radians(360.0 * i / _COMPASS_STEPS)
            north_km = math.cos(bearing) * radius
            east_km = math.sin(bearing) * radius
            candidate_lat = lat + north_km / 111.32
            lon_scale = max(0.2, math.cos(math.radians(lat)))
            candidate_lon = lon + east_km / (111.32 * lon_scale)
            if is_on_land(candidate_lat, candidate_lon) is True:
                return round(radius, 1)
        radius += step_km
    return None
