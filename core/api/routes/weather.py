# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Weather + mock layer data endpoints.

GET /api/v1/weather?lat=&lon=   - live/cached wind + ocean conditions
GET /api/v1/mock/ais            - synthetic AIS positions for demo/MOCK mode
"""
from __future__ import annotations

import logging
import math
import os
import random
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from core.ocean.cmems import fetch_ocean_batch, fetch_ocean_point

router = APIRouter()
logger = logging.getLogger(__name__)

_MOCK = os.getenv("MOCK", "false").lower() in ("1", "true", "yes")


@router.get("/api/v1/weather")
async def get_weather(lat: float = Query(35.5), lon: float = Query(14.0)):
    """
    Return current weather and ocean conditions for a lat/lon.
    In MOCK mode: synthetic values that drift slowly over time.
    Otherwise: tries Open-Meteo (free, no key required).
    """
    if _MOCK:
        return _mock_weather(lat, lon)
    return await _live_weather(lat, lon)


def _mock_weather(lat: float, lon: float) -> dict:
    t = time.monotonic()
    seed = int(abs(lat) * 100 + abs(lon) * 10) % 997

    wind_speed = 5.0 + 4.0 * abs(math.sin(t / 1800 + seed))
    wind_dir = (200 + 80 * math.sin(t / 3600 + seed)) % 360
    wave_h = 0.6 + 0.8 * abs(math.sin(t / 2400 + seed))
    water_temp = 17.0 + 3.0 * math.sin(math.radians(lat - 30))
    air_temp = water_temp + 2.0 + math.sin(t / 7200)
    current_spd = 0.10 + 0.08 * abs(math.sin(t / 4800 + seed))
    current_dir = (wind_dir + 30) % 360

    beaufort = _beaufort(wind_speed)
    return {
        "lat": lat, "lon": lon,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "mock",
        "wind": {
            "speed_ms": round(wind_speed, 2),
            "speed_kn": round(wind_speed * 1.944, 1),
            "direction_deg": round(wind_dir, 1),
            "direction_label": _compass(wind_dir),
            "beaufort": beaufort,
            "beaufort_label": _beaufort_label(beaufort),
        },
        "waves": {
            "significant_height_m": round(wave_h, 2),
            "period_s": round(3.0 + wave_h * 2.5, 1),
        },
        "ocean": {
            "water_temp_c": round(water_temp, 1),
            "current_speed_ms": round(current_spd, 3),
            "current_dir_deg": round(current_dir, 1),
        },
        "air": {
            "temp_c": round(air_temp, 1),
            "pressure_hpa": round(1013 + 5 * math.sin(t / 10800), 1),
            "visibility_km": round(15 - 5 * abs(math.sin(t / 5400 + seed)), 1),
        },
        "sar_conditions": {
            "drift_speed_ms": round(wind_speed * 0.035 + current_spd, 3),
            "drift_dir_deg": round((wind_dir + 180 + 15) % 360, 1),
            "survival_window_h": round(_survival_h(water_temp), 1),
            "sea_state": _sea_state(wave_h),
        },
    }


async def _live_weather(lat: float, lon: float) -> dict:
    import json as _json
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
            data = _json.loads(resp.read())
        cur = data.get("current", {})
        hr = data.get("hourly", {})
        ws = cur.get("wind_speed_10m", 5.0)
        wd = cur.get("wind_direction_10m", 270.0)
        at = cur.get("temperature_2m", 20.0)
        ocean = fetch_ocean_point(lat, lon)
        wv = hr.get("wave_height", [1.0])[0] if hr.get("wave_height") else 1.0
        if ocean and ocean.get("wave_height_m") is not None:
            wv = ocean["wave_height_m"]
        beaufort = _beaufort(ws)
        water_temp = ocean["water_temp_c"] if ocean else round(at - 2.0, 1)
        current_speed = ocean["current_speed_ms"] if ocean else 0.15
        current_dir = ocean["current_dir_deg"] if ocean else round((wd + 30) % 360, 1)
        source = "open-meteo+cmems" if ocean else "open-meteo"
        return {
            "lat": lat, "lon": lon,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "source": source,
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
                "pressure_hpa": round(cur.get("surface_pressure", 1013.0), 1),
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
        return {**_mock_weather(lat, lon), "source": f"mock (live failed: {exc})"}


async def _live_weather_batch(points: list[tuple[float, float]]) -> list[dict]:
    """
    Fetch weather for multiple grid points using Open-Meteo batch API.
    Single HTTP request returns data for all points.
    Falls back to mock on error.
    """
    import json as _json
    import urllib.request

    lats = ",".join(f"{lat:.3f}" for lat, _ in points)
    lons = ",".join(f"{lon:.3f}" for _, lon in points)
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lats}&longitude={lons}"
        f"&current=temperature_2m,wind_speed_10m,wind_direction_10m,surface_pressure"
        f"&hourly=wave_height"
        f"&wind_speed_unit=ms&forecast_days=1&timezone=UTC"
    )
    try:
        with urllib.request.urlopen(url, timeout=12) as resp:
            raw = _json.loads(resp.read())
        if isinstance(raw, dict):
            raw = [raw]
        ocean_batch = fetch_ocean_batch(points)
        results = []
        for i, (lat, lon) in enumerate(points):
            if i >= len(raw):
                results.append(_mock_weather(lat, lon))
                continue
            d = raw[i]
            cur = d.get("current", {})
            hr = d.get("hourly", {})
            ws = float(cur.get("wind_speed_10m", 5.0))
            wd = float(cur.get("wind_direction_10m", 270.0))
            at = float(cur.get("temperature_2m", 20.0))
            wv = float(hr.get("wave_height", [1.0])[0]) if hr.get("wave_height") else 1.0
            ocean = ocean_batch[i] if i < len(ocean_batch) else None
            if ocean and ocean.get("wave_height_m") is not None:
                wv = ocean["wave_height_m"]
            bf = _beaufort(ws)
            water_temp = ocean["water_temp_c"] if ocean else round(at - 2.0, 1)
            current_speed = ocean["current_speed_ms"] if ocean else 0.15
            current_dir = ocean["current_dir_deg"] if ocean else round((wd + 30) % 360, 1)
            results.append({
                "lat": lat, "lon": lon,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "source": "open-meteo+cmems" if ocean else "open-meteo",
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
                    "pressure_hpa": round(cur.get("surface_pressure", 1013.0), 1),
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
        logger.warning("Open-Meteo batch failed: %s  using mock", exc)
        return [_mock_weather(lat, lon) for lat, lon in points]


@router.get("/api/v1/weather/grid")
async def weather_grid(
    lat_min: float = Query(30.0),
    lat_max: float = Query(44.0),
    lon_min: float = Query(6.0),
    lon_max: float = Query(36.0),
    n: int = Query(7),
):
    """
    Return a GeoJSON grid of weather/wind/current data for map overlay.
    Used by the WeatherLayer frontend component to draw wind arrows.
    In live mode uses Open-Meteo batch API (single request for all grid points).
    """
    n = max(3, min(n, 10))
    grid_lats = [lat_min + (lat_max - lat_min) * i / max(n - 1, 1) for i in range(n)]
    grid_lons = [lon_min + (lon_max - lon_min) * j / max(n - 1, 1) for j in range(n)]

    points: list[tuple[float, float]] = []
    for lat in grid_lats:
        for lon in grid_lons:
            points.append((lat, lon))

    if _MOCK:
        weather_list = [_mock_weather(lat, lon) for lat, lon in points]
    else:
        weather_list = await _live_weather_batch(points)

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


_SHIPS = [
    {"mmsi": "247123456", "name": "ALAN KURDI", "type": "SAR", "lat": 35.88, "lon": 12.50, "sog": 12.0, "cog": 135},
    {"mmsi": "636091234", "name": "OCEAN VIKING", "type": "SAR", "lat": 37.50, "lon": 14.00, "sog": 9.0, "cog": 200},
    {"mmsi": "229123400", "name": "MSC FANTASIA", "type": "CARGO", "lat": 37.90, "lon": 15.10, "sog": 18.0, "cog": 310},
    {"mmsi": "255805960", "name": "COSTA SMERALDA", "type": "PASSENGER", "lat": 38.10, "lon": 13.30, "sog": 22.0, "cog": 270},
    {"mmsi": "310627000", "name": "MAERSK AICHI", "type": "CARGO", "lat": 36.80, "lon": 14.80, "sog": 16.0, "cog": 90},
    {"mmsi": "477123000", "name": "HMM GDANSK", "type": "CARGO", "lat": 35.20, "lon": 13.00, "sog": 14.5, "cog": 45},
    {"mmsi": "229456700", "name": "GDF SUEZ", "type": "TANKER", "lat": 37.00, "lon": 12.20, "sog": 11.0, "cog": 180},
    {"mmsi": "229100200", "name": "GUARDIA COSTIERA", "type": "SAR", "lat": 35.51, "lon": 12.62, "sog": 20.0, "cog": 25},
]

_TYPE_COLOR = {
    "SAR": "#22c55e",
    "CARGO": "#3b82f6",
    "PASSENGER": "#f59e0b",
    "TANKER": "#ef4444",
    "MILITARY": "#a78bfa",
}


@router.get("/api/v1/mock/ais")
async def mock_ais_vessels():
    """
    Return synthetic AIS vessel positions for MOCK mode.
    Positions drift slightly over time to simulate movement.
    """
    t = time.monotonic()
    features = []
    for ship in _SHIPS:
        elapsed_h = (t % 3600) / 3600
        spd_kmh = ship["sog"] * 1.852
        cog_rad = math.radians(ship["cog"])
        d_km = spd_kmh * elapsed_h
        dlat = (d_km * math.cos(cog_rad)) / 111.32
        dlon = (d_km * math.sin(cog_rad)) / (111.32 * math.cos(math.radians(ship["lat"])))

        cur_lat = ship["lat"] + dlat
        cur_lon = ship["lon"] + dlon

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [cur_lon, cur_lat]},
            "properties": {
                "mmsi": ship["mmsi"],
                "name": ship["name"],
                "type": ship["type"],
                "sog": ship["sog"],
                "cog": ship["cog"],
                "color": _TYPE_COLOR.get(ship["type"], "#71717a"),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
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
