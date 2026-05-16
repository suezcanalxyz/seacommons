# SPDX-License-Identifier: AGPL-3.0-or-later
"""Weather layer data endpoints."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
import json as _json_mod

router = APIRouter()
logger = logging.getLogger(__name__)

_weather_cache: dict[tuple, tuple[float, bytes]] = {}  # (lat_r, lon_r) → (ts, bytes)
_weather_grid_cache: dict[tuple, tuple[float, bytes]] = {}  # grid key → (ts, bytes)
_WEATHER_TTL = 600.0  # 10 minutes


def _coalesce_float(value, default: float) -> float:
    try:
        if value is None:
            return float(default)
        parsed = float(value)
        if not math.isfinite(parsed):
            return float(default)
        return parsed
    except (TypeError, ValueError):
        return float(default)

@router.get("/api/v1/weather")
async def get_weather(lat: float = Query(35.5), lon: float = Query(14.0)):
    key = (round(lat, 1), round(lon, 1))
    cached = _weather_cache.get(key)
    if cached and (time.monotonic() - cached[0]) < _WEATHER_TTL:
        return Response(content=cached[1], media_type="application/json")
    result = await asyncio.to_thread(_live_weather, lat, lon)
    payload = _json_mod.dumps(result).encode()
    _weather_cache[key] = (time.monotonic(), payload)
    return Response(content=payload, media_type="application/json")


def _live_weather(lat: float, lon: float) -> dict:
    import urllib.request

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat:.3f}&longitude={lon:.3f}"
            f"&current=temperature_2m,wind_speed_10m,wind_direction_10m,"
            f"surface_pressure,weather_code"
            f"&hourly=wave_height,ocean_current_velocity,ocean_current_direction"
            f"&wind_speed_unit=ms&forecast_days=1&timezone=UTC"
        )
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = _json_mod.loads(resp.read())
        cur = data.get("current", {})
        hr = data.get("hourly", {})
        ws = _coalesce_float(cur.get("wind_speed_10m"), 5.0)
        wd = _coalesce_float(cur.get("wind_direction_10m"), 270.0)
        at = _coalesce_float(cur.get("temperature_2m"), 20.0)
        wv = _coalesce_float(hr.get("wave_height", [1.0])[0] if hr.get("wave_height") else 1.0, 1.0)
        current_speed = _coalesce_float(
            hr.get("ocean_current_velocity", [0.15])[0] if hr.get("ocean_current_velocity") else 0.15, 0.15
        )
        current_dir = _coalesce_float(
            hr.get("ocean_current_direction", [None])[0] if hr.get("ocean_current_direction") else None,
            round((wd + 30) % 360, 1),
        )
        beaufort = _beaufort(ws)
        water_temp = round(at - 2.0, 1)
        return {
            "lat": lat, "lon": lon,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "source": "open-meteo",
            "wind": {
                "speed_ms": round(ws, 2),
                "speed_kn": round(ws * 1.944, 1),
                "direction_deg": round(wd, 1),
                "direction_label": _compass(wd),
                "beaufort": beaufort,
                "beaufort_label": _beaufort_label(beaufort),
            },
            "waves": {
                "significant_height_m": round(float(wv), 2),
                "period_s": round(3.0 + float(wv) * 2.5, 1),
            },
            "ocean": {
                "water_temp_c": round(water_temp, 1),
                "current_speed_ms": round(current_speed, 3),
                "current_dir_deg": round(current_dir, 1),
            },
            "air": {
                "temp_c": round(at, 1),
                "pressure_hpa": round(_coalesce_float(cur.get("surface_pressure"), 1013.0), 1),
                "visibility_km": 15.0,
            },
            "sar_conditions": {
                "drift_speed_ms": round(ws * 0.035 + current_speed, 3),
                "drift_dir_deg": round((wd + 180 + 15) % 360, 1),
                "survival_window_h": round(_survival_h(water_temp), 1),
                "sea_state": _sea_state(float(wv)),
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Real weather data unavailable: {exc}") from exc


def _live_weather_batch(points: list[tuple[float, float]]) -> list[dict]:
    """Fetch weather for multiple grid points using a single Open-Meteo request."""
    import json as _json
    import urllib.request

    lats = ",".join(f"{lat:.3f}" for lat, _ in points)
    lons = ",".join(f"{lon:.3f}" for _, lon in points)
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lats}&longitude={lons}"
        f"&current=temperature_2m,wind_speed_10m,wind_direction_10m,surface_pressure"
        f"&hourly=wave_height,ocean_current_velocity,ocean_current_direction"
        f"&wind_speed_unit=ms&forecast_days=1&timezone=UTC"
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            raw = _json.loads(resp.read())
        if isinstance(raw, dict):
            raw = [raw]
        results = []
        for i, (lat, lon) in enumerate(points):
            if i >= len(raw):
                raise RuntimeError(f"Open-Meteo batch payload incomplete at index {i}")
            d = raw[i]
            cur = d.get("current", {})
            hr = d.get("hourly", {})
            ws = _coalesce_float(cur.get("wind_speed_10m"), 5.0)
            wd = _coalesce_float(cur.get("wind_direction_10m"), 270.0)
            at = _coalesce_float(cur.get("temperature_2m"), 20.0)
            wv = _coalesce_float(hr.get("wave_height", [1.0])[0] if hr.get("wave_height") else 1.0, 1.0)
            bf = _beaufort(ws)
            water_temp = round(at - 2.0, 1)
            current_speed = _coalesce_float(
                hr.get("ocean_current_velocity", [0.15])[0] if hr.get("ocean_current_velocity") else 0.15,
                0.15,
            )
            current_dir = _coalesce_float(
                hr.get("ocean_current_direction", [round((wd + 30) % 360, 1)])[0]
                if hr.get("ocean_current_direction")
                else round((wd + 30) % 360, 1),
                round((wd + 30) % 360, 1),
            )
            results.append({
                "lat": lat, "lon": lon,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "source": "open-meteo",
                "wind": {
                    "speed_ms": round(ws, 2),
                    "speed_kn": round(ws * 1.944, 1),
                    "direction_deg": round(wd, 1),
                    "direction_label": _compass(wd),
                    "beaufort": bf,
                    "beaufort_label": _beaufort_label(bf),
                },
                "waves": {
                    "significant_height_m": round(wv, 2),
                    "period_s": round(3.0 + wv * 2.5, 1),
                },
                "ocean": {
                    "water_temp_c": round(water_temp, 1),
                    "current_speed_ms": round(current_speed, 3),
                    "current_dir_deg": round(current_dir, 1),
                },
                "air": {
                    "temp_c": round(at, 1),
                    "pressure_hpa": round(_coalesce_float(cur.get("surface_pressure"), 1013.0), 1),
                    "visibility_km": 15.0,
                },
                "sar_conditions": {
                    "drift_speed_ms": round(ws * 0.035 + current_speed, 3),
                    "drift_dir_deg": round((wd + 180 + 15) % 360, 1),
                    "survival_window_h": round(_survival_h(water_temp), 1),
                    "sea_state": _sea_state(wv),
                },
            })
        return results
    except Exception as exc:
        logger.warning("Open-Meteo batch failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Real weather grid unavailable: {exc}") from exc


@router.get("/api/v1/weather/grid")
async def weather_grid(
    lat_min: float = Query(30.0),
    lat_max: float = Query(44.0),
    lon_min: float = Query(6.0),
    lon_max: float = Query(36.0),
    n: int = Query(4),
):
    """Return a GeoJSON grid of real weather and current data for the map overlay."""
    n_clamped = max(3, min(n, 6))  # hard cap at 6 (36 pts) — Open-Meteo batch limit
    # Round bbox to 1° grid so nearby views share the same cache entry.
    # Fine rounding (0.1°) caused constant cache misses on every small pan.
    key = (round(lat_min), round(lat_max), round(lon_min), round(lon_max), n_clamped)
    cached = _weather_grid_cache.get(key)
    if cached and (time.monotonic() - cached[0]) < _WEATHER_TTL:
        return Response(content=cached[1], media_type="application/json")

    result = await asyncio.to_thread(_weather_grid_payload, lat_min, lat_max, lon_min, lon_max, n_clamped)
    payload = _json_mod.dumps(result).encode()
    _weather_grid_cache[key] = (time.monotonic(), payload)
    return Response(content=payload, media_type="application/json")


def _weather_grid_payload(
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    n: int,
):
    n = max(3, min(n, 10))
    grid_lats = [lat_min + (lat_max - lat_min) * i / max(n - 1, 1) for i in range(n)]
    grid_lons = [lon_min + (lon_max - lon_min) * j / max(n - 1, 1) for j in range(n)]

    points: list[tuple[float, float]] = []
    for lat in grid_lats:
        for lon in grid_lons:
            points.append((lat, lon))

    weather_list = _live_weather_batch(points)

    features = []
    for (lat, lon), w in zip(points, weather_list):
        sar_cond = (
            w["waves"]["significant_height_m"] > 2.0 or
            w["wind"]["beaufort"] >= 6 or
            w["sar_conditions"]["survival_window_h"] < 6.0
        )
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 3), round(lat, 3)]},
            "properties": {
                "wind_speed_ms": w["wind"]["speed_ms"],
                "wind_dir_deg": w["wind"]["direction_deg"],
                "wind_kn": w["wind"]["speed_kn"],
                "beaufort": w["wind"]["beaufort"],
                "wave_height_m": w["waves"]["significant_height_m"],
                "water_temp_c": w["ocean"]["water_temp_c"],
                "current_speed_ms": w["ocean"]["current_speed_ms"],
                "current_dir_deg": w["ocean"]["current_dir_deg"],
                "survival_window_h": w["sar_conditions"]["survival_window_h"],
                "drift_speed_ms": w["sar_conditions"]["drift_speed_ms"],
                "drift_dir_deg": w["sar_conditions"]["drift_dir_deg"],
                "sar_condition": sar_cond,
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "grid": {
            "n": n,
            "lat_min": lat_min,
            "lat_max": lat_max,
            "lon_min": lon_min,
            "lon_max": lon_max,
        },
    }

def _beaufort(ws: float) -> int:
    thresholds = [0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7]
    for i, threshold in enumerate(thresholds):
        if ws < threshold:
            return i
    return 12


def _beaufort_label(bf: int) -> str:
    labels = [
        "Calma", "Bava", "Brezza", "Brezza leggera", "Brezza moderata",
        "Brezza fresca", "Brezza forte", "Vento forte", "Burrasca moderata",
        "Burrasca forte", "Tempesta", "Tempesta violenta", "Uragano",
    ]
    return labels[min(bf, 12)]


def _compass(deg: float) -> str:
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
    return dirs[int((deg + 11.25) / 22.5) % 16]


def _survival_h(water_temp_c: float) -> float:
    table = [(0, 0.5), (5, 1.0), (10, 2.0), (15, 6.0), (20, 12.0), (25, 24.0), (30, 40.0)]
    temp = max(0.0, min(water_temp_c, 30.0))
    for i in range(len(table) - 1):
        t0, h0 = table[i]
        t1, h1 = table[i + 1]
        if t0 <= temp <= t1:
            return h0 + (temp - t0) / (t1 - t0) * (h1 - h0)
    return table[-1][1]


def _sea_state(wave_h: float) -> str:
    if wave_h < 0.1:
        return "Glassy"
    if wave_h < 0.5:
        return "Rippled"
    if wave_h < 1.25:
        return "Slight"
    if wave_h < 2.5:
        return "Moderate"
    if wave_h < 4.0:
        return "Rough"
    if wave_h < 6.0:
        return "Very rough"
    return "High"
