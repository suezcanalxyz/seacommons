# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run real OpenDrift trajectories from JSON stdin and emit GeoJSON JSON."""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from opendrift.models.leeway import Leeway
from opendrift.readers import reader_constant


def _parse_time(value: str) -> datetime:
    # OpenDrift 1.14.9 requires tz-naive UTC; tz-aware causes state_to_buffer crash
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _mean_path(result_dataset: Any) -> list[list[float]]:
    # shape is (trajectory, time) — axis 0 = particles, axis 1 = timesteps
    lons = result_dataset.lon.values
    lats = result_dataset.lat.values
    n_traj, n_time = lons.shape
    coords: list[list[float]] = []
    for t_index in range(n_time):
        col_lon = lons[:, t_index]
        col_lat = lats[:, t_index]
        pts = [
            (float(col_lon[i]), float(col_lat[i]))
            for i in range(n_traj)
            if not math.isnan(col_lon[i]) and not math.isnan(col_lat[i])
        ]
        if not pts:
            continue
        coords.append([
            sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts),
        ])
    return coords


def _convex_hull(points: list[tuple[float, float]]) -> list[list[float]]:
    unique = sorted(set(points))
    if len(unique) <= 1:
        return [[p[0], p[1]] for p in unique]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: list[tuple[float, float]] = []
    for p in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    hull = lower[:-1] + upper[:-1]
    return [[p[0], p[1]] for p in hull]


def _cloud_polygon(result_dataset: Any, time_index: int) -> dict[str, Any]:
    # shape is (trajectory, time) — clamp time_index to axis 1
    lons = result_dataset.lon.values
    lats = result_dataset.lat.values
    n_traj, n_time = lons.shape
    idx = max(0, min(time_index, n_time - 1))
    points: list[tuple[float, float]] = []
    for e_index in range(n_traj):
        lon = float(lons[e_index, idx])
        lat = float(lats[e_index, idx])
        if math.isnan(lon) or math.isnan(lat):
            continue
        points.append((lon, lat))

    if not points:
        return {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[]]},
            "properties": {"hours": 0},
        }

    if len(points) == 1:
        lon, lat = points[0]
        eps = 0.01
        hull = [
            [lon - eps, lat - eps],
            [lon + eps, lat - eps],
            [lon + eps, lat + eps],
            [lon - eps, lat + eps],
        ]
    else:
        hull = _convex_hull(points)

    if hull[0] != hull[-1]:
        hull.append(hull[0])

    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [hull]},
        "properties": {"hours": idx},
    }


def _point_feature(coord: list[float], hours: int) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": coord},
        "properties": {"type": "impact_point", "hours": hours},
    }


def _hours_to_index(hours: int, output_hours: list[int]) -> int:
    best_idx = 0
    best_diff = 10**9
    for idx, current in enumerate(output_hours):
        diff = abs(current - hours)
        if diff < best_diff:
            best_idx = idx
            best_diff = diff
    return best_idx


def run(payload: dict[str, Any]) -> dict[str, Any]:
    start_time = _parse_time(payload["time_utc"])
    duration_h = int(payload.get("duration_h", 24))
    env = payload.get("environment", {})
    particles = int(payload.get("particles", 128))
    time_step_seconds = int(payload.get("time_step_seconds", 900))
    output_seconds = int(payload.get("time_step_output_seconds", 3600))
    object_type = int(payload.get("object_type", 26))

    simulation = Leeway(loglevel=20)
    simulation.set_config("drift:stokes_drift", False)
    simulation.set_config("general:time_step_minutes", max(1, time_step_seconds // 60))
    simulation.set_config("general:time_step_output_minutes", max(1, output_seconds // 60))

    simulation.add_reader(
        reader_constant.Reader(
            {
                "x_wind": float(env["x_wind"]),
                "y_wind": float(env["y_wind"]),
                "x_sea_water_velocity": float(env["x_sea_water_velocity"]),
                "y_sea_water_velocity": float(env["y_sea_water_velocity"]),
                "land_binary_mask": int(env.get("land_binary_mask", 0)),
            }
        )
    )

    simulation.seed_elements(
        lon=float(payload["lon"]),
        lat=float(payload["lat"]),
        time=start_time,
        radius=float(payload.get("seed_radius_m", 150)),
        number=particles,
        object_type=object_type,
    )
    simulation.run(
        duration=timedelta(hours=duration_h),
        time_step=time_step_seconds,
        time_step_output=output_seconds,
    )

    result = simulation.result
    coords = _mean_path(result)
    if len(coords) < 2:
        raise RuntimeError("OpenDrift produced insufficient trajectory points")

    output_hours = [int(i * output_seconds / 3600) for i in range(len(coords))]
    idx_6 = _hours_to_index(6, output_hours)
    idx_12 = _hours_to_index(12, output_hours)
    idx_24 = _hours_to_index(min(24, duration_h), output_hours)

    trajectory = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {"type": "trajectory"},
    }
    impact = {
        "type": "FeatureCollection",
        "features": [_point_feature(coords[-1], duration_h)],
    }
    return {
        "trajectory": trajectory,
        "cone_6h": _cloud_polygon(result, idx_6),
        "cone_12h": _cloud_polygon(result, idx_12),
        "cone_24h": _cloud_polygon(result, idx_24),
        "impact_point": impact,
        "metadata": {
            "domain": payload.get("domain", "ocean_sar"),
            "start_time": start_time.isoformat(),
            "duration_h": duration_h,
            "model": "OpenDrift Leeway",
            "particles": particles,
            "object_type": object_type,
            "forcing": {
                "x_wind": float(env["x_wind"]),
                "y_wind": float(env["y_wind"]),
                "x_sea_water_velocity": float(env["x_sea_water_velocity"]),
                "y_sea_water_velocity": float(env["y_sea_water_velocity"]),
            },
        },
    }


if __name__ == "__main__":
    payload = json.loads(sys.stdin.read())
    json.dump(run(payload), sys.stdout)
