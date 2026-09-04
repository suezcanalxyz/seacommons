# SPDX-License-Identifier: AGPL-3.0-or-later
"""AIS reception-quality baseline (docs/fixes.md M4.2).

Whether a reporting gap is a genuine anomaly or an artefact of patchy AIS
reception can't be judged from the gap alone -- the same silence means
something different in a dense, well-covered shipping lane than it does
150nm offshore with one satellite pass an hour. This module computes that
context from the platform's own reception history (core.vessels.track_store),
not from a fixed global threshold.

Wired into core.mda.watch.scan_gaps() (docs/fixes.md M14.1) as the
reception-quality context behind each gap's core.mda.gap_reason
classification, replacing scan_gaps()'s former hard vessel-class
exclusions.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

_NM_PER_DEGREE_LAT = 60.0405  # ~ nautical miles per degree of latitude

# Local receiver/message density buckets -- how many distinct nearby
# vessels reported at all in the comparison window. Deliberately coarse
# (three buckets, not a raw count) since the boundary is a judgement call,
# not a measured constant.
_CONGESTION_LOW_MAX = 2
_CONGESTION_MEDIUM_MAX = 14


@dataclass(frozen=True)
class CoverageBaseline:
    mmsi: str
    at: datetime
    source_health: str  # "healthy" | "unknown" (see docstring below)
    expected_reporting_interval_s: Optional[float]
    local_receiver_density: int
    neighbour_message_ratio: Optional[float]
    coast_distance_km: Optional[float]
    congestion: str  # "low" | "medium" | "high" | "unknown"
    jamming_context: Optional[float]
    preceding_track_density: int


def _bbox_for_radius(lat: float, lon: float, radius_nm: float) -> tuple[float, float, float, float]:
    """(min_lon, min_lat, max_lon, max_lat) -- a simple equirectangular box,
    not a precise circle. Good enough for a comparison-window query; the
    same approximation core.intel.landmask's radial search already makes."""
    d_lat = radius_nm / _NM_PER_DEGREE_LAT
    lon_scale = max(0.2, math.cos(math.radians(lat)))
    d_lon = radius_nm / (_NM_PER_DEGREE_LAT * lon_scale)
    return (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)


def compute_coverage_baseline(
    mmsi: str,
    lat: float,
    lon: float,
    *,
    at: Optional[datetime] = None,
    window_min: float = 60.0,
    radius_nm: float = 25.0,
) -> CoverageBaseline:
    """Best-effort, never raises -- every field degrades to its honest
    "don't know" value (None/"unknown") rather than fabricating one when a
    dependency (track_store, jamming, landmask) is unavailable.
    """
    at = at or datetime.now(timezone.utc)
    window_start = at - timedelta(minutes=window_min)

    preceding_track_density = 0
    local_receiver_density = 0
    neighbour_message_ratio: Optional[float] = None
    try:
        from core.vessels.track_store import track_store

        own_rows = track_store.track(mmsi, since=window_start, until=at)
        preceding_track_density = len(own_rows)

        bbox = _bbox_for_radius(lat, lon, radius_nm)
        nearby_rows = track_store.positions_between(window_start, at, bbox=bbox)
        per_mmsi_counts: dict[str, int] = {}
        for row in nearby_rows:
            row_mmsi = row.get("mmsi")
            if row_mmsi:
                per_mmsi_counts[row_mmsi] = per_mmsi_counts.get(row_mmsi, 0) + 1
        neighbour_counts = [count for m, count in per_mmsi_counts.items() if m != mmsi]
        local_receiver_density = len(neighbour_counts)
        if neighbour_counts:
            median = statistics.median(neighbour_counts)
            if median > 0:
                neighbour_message_ratio = round(preceding_track_density / median, 3)
    except Exception:
        pass

    if local_receiver_density == 0:
        congestion = "unknown"
    elif local_receiver_density <= _CONGESTION_LOW_MAX:
        congestion = "low"
    elif local_receiver_density <= _CONGESTION_MEDIUM_MAX:
        congestion = "medium"
    else:
        congestion = "high"

    jamming_context: Optional[float] = None
    try:
        from core.mda.jamming import jamming

        jamming_context = jamming.in_jamming_zone(lat, lon, at)
    except Exception:
        pass

    coast_distance_km: Optional[float] = None
    try:
        from core.intel.landmask import distance_to_coast_km

        coast_distance_km = distance_to_coast_km(lat, lon)
    except Exception:
        pass

    expected_reporting_interval_s: Optional[float] = None
    try:
        from core.config import config

        expected_reporting_interval_s = float(getattr(config, "VESSEL_TRACK_MIN_INTERVAL_S", 60))
    except Exception:
        pass

    # v0: "healthy" when there is any corroborating nearby traffic at all in
    # the window, "unknown" otherwise. "degraded" (a feed-wide, AOI-level
    # reception drop distinguishable from one vessel's own silence) needs a
    # historical per-AOI reporting-rate baseline this module doesn't build
    # yet -- reserved for a follow-up rather than guessed at here.
    source_health = "healthy" if local_receiver_density > 0 else "unknown"

    return CoverageBaseline(
        mmsi=mmsi,
        at=at,
        source_health=source_health,
        expected_reporting_interval_s=expected_reporting_interval_s,
        local_receiver_density=local_receiver_density,
        neighbour_message_ratio=neighbour_message_ratio,
        coast_distance_km=coast_distance_km,
        congestion=congestion,
        jamming_context=jamming_context,
        preceding_track_density=preceding_track_density,
    )
