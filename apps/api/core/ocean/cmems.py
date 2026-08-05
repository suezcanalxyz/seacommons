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


def fetch_current_point(lat: float, lon: float) -> dict[str, Any] | None:
    if not cmems_enabled():
        return None

    try:
        copernicusmarine = _load_copernicusmarine()
    except Exception as exc:
        logger.warning("CMEMS unavailable: %s", exc)
        return None

    norm_lon = _normalize_lon(lon)
    pad = 0.12
    start = (datetime.now(timezone.utc) - timedelta(hours=18)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()

    try:
        current_ds = copernicusmarine.open_dataset(
            dataset_id=config.CMEMS_CURRENT_DATASET,
            username=config.CMEMS_USERNAME,
            password=config.CMEMS_PASSWORD,
            variables=["uo", "vo"],
            minimum_longitude=norm_lon - pad,
            maximum_longitude=norm_lon + pad,
            minimum_latitude=lat - pad,
            maximum_latitude=lat + pad,
            minimum_depth=0.0,
            maximum_depth=1.0,
            start_datetime=start,
            end_datetime=end,
            coordinates_selection_method="nearest",
        )
        u = _sample_value(current_ds, "uo", lat, norm_lon)
        v = _sample_value(current_ds, "vo", lat, norm_lon)
    except Exception as exc:
        logger.warning("CMEMS current fetch failed for %.3f,%.3f: %s", lat, lon, exc)
        return None

    current_speed = math.hypot(u, v)
    current_dir = (math.degrees(math.atan2(u, v)) + 360.0) % 360.0
    return {
        "current_speed_ms": round(current_speed, 3),
        "current_dir_deg": round(current_dir, 1),
        "source": "cmems-current",
    }


def fetch_ocean_batch(
    points: list[tuple[float, float]], *, at: datetime | None = None,
) -> list[dict[str, Any] | None]:
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
    now = datetime.now(timezone.utc)
    # Default window covers "now"; widen it to also cover `at` when that
    # falls outside it, so a request for conditions at a report's own
    # (possibly days-old) timestamp doesn't silently fall back to "latest".
    window_start = now - timedelta(days=2)
    window_end = now + timedelta(days=1)
    if at is not None:
        window_start = min(window_start, at - timedelta(hours=6))
        window_end = max(window_end, at + timedelta(hours=6))
    start = window_start.isoformat()
    end = window_end.isoformat()

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
            u = _sample_value(current_ds, "uo", lat, norm_lon, at=at)
            v = _sample_value(current_ds, "vo", lat, norm_lon, at=at)
            temp = _sample_value(temp_ds, "thetao", lat, norm_lon, at=at)
            wave = _sample_value(wave_ds, "VHM0", lat, norm_lon, at=at)

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


def _sample_value(
    ds, variable: str, lat: float, lon: float, *, at: datetime | None = None,
) -> float:
    da = ds[variable]
    for depth_name in ("depth", "deptho", "depthu"):
        if depth_name in da.dims:
            da = da.isel({depth_name: 0})
            break
    for time_name in ("time", "valid_time"):
        if time_name in da.dims:
            if at is not None:
                da = da.sel({time_name: at}, method="nearest")
            else:
                da = da.isel({time_name: -1})
            break
    lat_name = _coord_name(da, "latitude", "lat")
    lon_name = _coord_name(da, "longitude", "lon")
    selected = da.sel({lat_name: lat, lon_name: lon}, method="nearest")
    value = float(selected.values)
    if not math.isfinite(value):
        raise ValueError(f"Non-finite CMEMS value for {variable}")
    return value


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
