# SPDX-License-Identifier: AGPL-3.0-or-later
"""Copernicus Marine helpers for live ocean conditions."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from core.config import config

logger = logging.getLogger(__name__)


def cmems_enabled() -> bool:
    return bool(config.CMEMS_USERNAME and config.CMEMS_PASSWORD)


def fetch_ocean_point(lat: float, lon: float) -> dict[str, Any] | None:
    results = fetch_ocean_batch([(lat, lon)])
    return results[0] if results else None


def fetch_ocean_batch(points: list[tuple[float, float]]) -> list[dict[str, Any] | None]:
    if not points or not cmems_enabled():
        return [None for _ in points]

    try:
        copernicusmarine = _load_copernicusmarine()
    except Exception as exc:
        logger.warning("CMEMS unavailable: %s", exc)
        return [None for _ in points]

    lats = [lat for lat, _ in points]
    lons = [_normalize_lon(lon) for _, lon in points]
    pad = 0.2
    start = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    try:
        current_ds = copernicusmarine.open_dataset(
            dataset_id=config.CMEMS_CURRENT_DATASET,
            username=config.CMEMS_USERNAME,
            password=config.CMEMS_PASSWORD,
            variables=["uo", "vo"],
            minimum_longitude=min(lons) - pad,
            maximum_longitude=max(lons) + pad,
            minimum_latitude=min(lats) - pad,
            maximum_latitude=max(lats) + pad,
            minimum_depth=0.0,
            maximum_depth=1.0,
            start_datetime=start,
            end_datetime=end,
            coordinates_selection_method="nearest",
        )
        temp_ds = copernicusmarine.open_dataset(
            dataset_id=config.CMEMS_TEMPERATURE_DATASET,
            username=config.CMEMS_USERNAME,
            password=config.CMEMS_PASSWORD,
            variables=["thetao"],
            minimum_longitude=min(lons) - pad,
            maximum_longitude=max(lons) + pad,
            minimum_latitude=min(lats) - pad,
            maximum_latitude=max(lats) + pad,
            minimum_depth=0.0,
            maximum_depth=1.0,
            start_datetime=start,
            end_datetime=end,
            coordinates_selection_method="nearest",
        )
        wave_ds = copernicusmarine.open_dataset(
            dataset_id=config.CMEMS_WAVE_DATASET,
            username=config.CMEMS_USERNAME,
            password=config.CMEMS_PASSWORD,
            variables=["VHM0"],
            minimum_longitude=min(lons) - pad,
            maximum_longitude=max(lons) + pad,
            minimum_latitude=min(lats) - pad,
            maximum_latitude=max(lats) + pad,
            start_datetime=start,
            end_datetime=end,
            coordinates_selection_method="nearest",
        )
    except Exception as exc:
        logger.warning("CMEMS fetch failed: %s", exc)
        return [None for _ in points]

    results: list[dict[str, Any] | None] = []
    for lat, lon in points:
        try:
            norm_lon = _normalize_lon(lon)
            u = _sample_value(current_ds, "uo", lat, norm_lon)
            v = _sample_value(current_ds, "vo", lat, norm_lon)
            temp = _sample_value(temp_ds, "thetao", lat, norm_lon)
            wave = _sample_value(wave_ds, "VHM0", lat, norm_lon)

            current_speed = math.hypot(u, v)
            current_dir = (math.degrees(math.atan2(u, v)) + 360.0) % 360.0
            results.append({
                "water_temp_c": round(temp, 2),
                "current_speed_ms": round(current_speed, 3),
                "current_dir_deg": round(current_dir, 1),
                "wave_height_m": round(wave, 2),
                "source": "cmems",
            })
        except Exception as exc:
            logger.debug("CMEMS sample failed for %.3f,%.3f: %s", lat, lon, exc)
            results.append(None)
    return results


@lru_cache(maxsize=1)
def _load_copernicusmarine():
    import copernicusmarine

    return copernicusmarine


def _sample_value(ds, variable: str, lat: float, lon: float) -> float:
    da = ds[variable]
    for depth_name in ("depth", "deptho", "depthu"):
        if depth_name in da.dims:
            da = da.isel({depth_name: 0})
            break
    for time_name in ("time", "valid_time"):
        if time_name in da.dims:
            da = da.isel({time_name: -1})
            break
    lat_name = _coord_name(da, "latitude", "lat")
    lon_name = _coord_name(da, "longitude", "lon")
    selected = da.sel({lat_name: lat, lon_name: lon}, method="nearest")
    return float(selected.values)


def _coord_name(ds, *names: str) -> str:
    for name in names:
        if name in ds.coords or name in ds.dims:
            return name
    raise KeyError(f"Missing coordinate, expected one of: {names}")


def _normalize_lon(lon: float) -> float:
    while lon > 180.0:
        lon -= 360.0
    while lon < -180.0:
        lon += 360.0
    return lon
