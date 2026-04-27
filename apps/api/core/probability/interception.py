# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Vessel interception calculator.

Given a distress position and a responding asset, compute:
- Time-to-intercept (hours)
- Whether interception is possible before survival window closes
- Optimal intercept heading

Uses dead-reckoning: both the distress object (drifting) and the asset
(steaming at constant speed/heading) are propagated forward in time.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class Asset:
    """A SAR asset (vessel, aircraft, helicopter) that can respond."""
    asset_id: str
    lat: float
    lon: float
    speed_kn: float               # knots
    endurance_h: float = 24.0     # hours of operation before needing to return
    asset_type: str = "vessel"    # vessel | aircraft | helicopter


@dataclass
class InterceptionResult:
    asset_id: str
    distance_nm: float
    time_to_intercept_h: float
    intercept_lat: float
    intercept_lon: float
    heading_deg: float
    feasible: bool                # True if within endurance and survival window


_NM_PER_DEG_LAT = 60.0           # 1° latitude ≈ 60 nautical miles


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    R = 3440.065  # Earth radius in nm
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2 (degrees, 0 = N)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    x = math.sin(dlam) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _project(lat: float, lon: float, heading_deg: float, distance_nm: float
             ) -> tuple[float, float]:
    """Project a point by distance_nm along heading_deg (flat-earth approx)."""
    dlat = distance_nm * math.cos(math.radians(heading_deg)) / _NM_PER_DEG_LAT
    dlon = (distance_nm * math.sin(math.radians(heading_deg))
            / (_NM_PER_DEG_LAT * math.cos(math.radians(lat)) + 1e-9))
    return lat + dlat, lon + dlon


def compute_interception(
    distress_lat: float,
    distress_lon: float,
    drift_speed_kn: float,
    drift_heading_deg: float,
    assets: list[Asset],
    survival_window_h: float,
) -> list[InterceptionResult]:
    """
    For each asset, compute time-to-intercept assuming:
    - Distress object drifts at drift_speed_kn on drift_heading_deg
    - Asset steams directly toward the projected intercept point

    Returns results sorted by time_to_intercept_h ascending.
    """
    results: list[InterceptionResult] = []

    for asset in assets:
        # Iterative dead-reckoning: find time t where asset can reach the
        # drifted distress position
        t = 0.0
        for _ in range(50):   # converge in ≤ 50 iterations
            # Project distress object forward by t hours
            drift_nm = drift_speed_kn * t
            proj_lat, proj_lon = _project(
                distress_lat, distress_lon, drift_heading_deg, drift_nm)

            # Distance from asset to projected distress position
            dist_nm = _haversine_nm(asset.lat, asset.lon, proj_lat, proj_lon)
            t_new = dist_nm / max(0.1, asset.speed_kn)

            if abs(t_new - t) < 1e-4:
                t = t_new
                break
            t = t_new

        proj_lat, proj_lon = _project(
            distress_lat, distress_lon, drift_heading_deg, drift_speed_kn * t)
        dist_nm = _haversine_nm(asset.lat, asset.lon, proj_lat, proj_lon)
        heading = _bearing_deg(asset.lat, asset.lon, proj_lat, proj_lon)

        feasible = (t <= asset.endurance_h) and (t <= survival_window_h)

        results.append(InterceptionResult(
            asset_id=asset.asset_id,
            distance_nm=round(dist_nm, 2),
            time_to_intercept_h=round(t, 3),
            intercept_lat=round(proj_lat, 5),
            intercept_lon=round(proj_lon, 5),
            heading_deg=round(heading, 1),
            feasible=feasible,
        ))

    results.sort(key=lambda r: r.time_to_intercept_h)
    return results
