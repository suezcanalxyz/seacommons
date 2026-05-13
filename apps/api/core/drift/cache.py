# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local cache for ocean currents, wind, tiles, and RINEX data."""
from __future__ import annotations
import concurrent.futures
import json
import math
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

from core.config import config
from core.ocean.cmems import fetch_current_point

CACHE_DIR = Path.home() / ".suezcanal" / "cache"
CACHE_TTL_S = 48 * 3600


class CacheManager:
    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.cache_dir / name

    def is_stale(self, asset: str, ttl: int = CACHE_TTL_S) -> bool:
        p = self._path(f"{asset}.json")
        if not p.exists():
            return True
        return (time.time() - p.stat().st_mtime) > ttl

    def update(self, region_lat: float, region_lon: float, radius_km: float = 500) -> None:
        self._update_wind(region_lat, region_lon)
        self._path("region.json").write_text(json.dumps({
            "lat": region_lat, "lon": region_lon,
            "radius_km": radius_km, "updated": time.time(),
        }))

    def _update_wind(self, lat: float, lon: float) -> None:
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat:.3f}&longitude={lon:.3f}"
                f"&hourly=wind_speed_10m,wind_direction_10m,surface_pressure"
                f"&wind_speed_unit=ms&forecast_days=2"
            )
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            self._path("wind_cache.json").write_text(
                json.dumps({"lat": lat, "lon": lon, "data": data, "ts": time.time()})
            )
        except Exception as exc:
            print(f"[cache] wind update failed: {exc}")

    def get_wind(self, lat: float, lon: float, time_utc: Optional[str] = None) -> dict[str, Any]:
        p = self._path("wind_cache.json")
        if p.exists():
            try:
                cached = json.loads(p.read_text())
                hourly = cached.get("data", {}).get("hourly", {})
                times = hourly.get("time", [])
                speeds = hourly.get("wind_speed_10m", [])
                dirs = hourly.get("wind_direction_10m", [])
                if times:
                    idx = 0
                    if time_utc:
                        for i, t in enumerate(times):
                            if t >= time_utc[:16]:
                                idx = i
                                break
                    return {
                        "wind_speed_ms": speeds[idx] if idx < len(speeds) else 5.0,
                        "wind_dir_deg": dirs[idx] if idx < len(dirs) else 270.0,
                        "source": "cache",
                    }
            except Exception:
                pass
        raise RuntimeError("No real wind cache available")

    def get_wind_live(self, lat: float, lon: float) -> dict[str, Any]:
        """Fetch current wind directly from Open-Meteo for this exact position."""
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat:.3f}&longitude={lon:.3f}"
                f"&current=wind_speed_10m,wind_direction_10m"
                f"&wind_speed_unit=ms&forecast_days=1"
            )
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = json.loads(resp.read())
            cur = data.get("current", {})
            ws = float(cur.get("wind_speed_10m", 5.0))
            wd = float(cur.get("wind_direction_10m", 270.0))
            return {"wind_speed_ms": ws, "wind_dir_deg": wd, "source": "open-meteo-live"}
        except Exception as exc:
            print(f"[cache] live wind fetch failed for {lat},{lon}: {exc}")
            return self.get_wind(lat, lon)

    def get_wind_forecast_series(self, lat: float, lon: float, hours: int = 48) -> list[dict[str, Any]]:
        """Fetch Open-Meteo hourly wind forecast, returns list of per-hour dicts."""
        forecast_days = max(2, (hours // 24) + 1)
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat:.3f}&longitude={lon:.3f}"
                f"&hourly=wind_speed_10m,wind_direction_10m"
                f"&wind_speed_unit=ms&forecast_days={forecast_days}"
            )
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            hourly = data.get("hourly", {})
            speeds = hourly.get("wind_speed_10m", [])
            dirs   = hourly.get("wind_direction_10m", [])
            series = []
            for h in range(min(hours, len(speeds))):
                ws  = float(speeds[h]) if h < len(speeds) else 5.0
                wd  = float(dirs[h])   if h < len(dirs)   else 270.0
                rad = math.radians(wd)
                series.append({
                    "h": h,
                    "wind_speed_ms": min(max(ws, 0.5), 30.0),
                    "wind_dir_deg":  wd,
                    "wind_x": ws * math.sin(rad),
                    "wind_y": ws * math.cos(rad),
                })
            if series:
                return series
        except Exception as exc:
            print(f"[cache] forecast series failed for {lat},{lon}: {exc}")
        return self._wind_series_from_cache(hours=hours)

    def _wind_series_from_cache(self, hours: int) -> list[dict[str, Any]]:
        p = self._path("wind_cache.json")
        if not p.exists():
            raise RuntimeError("No real wind forecast cache available")
        cached = json.loads(p.read_text())
        hourly = cached.get("data", {}).get("hourly", {})
        speeds = hourly.get("wind_speed_10m", [])
        dirs = hourly.get("wind_direction_10m", [])
        series = []
        for h in range(min(hours, len(speeds))):
            ws = float(speeds[h])
            wd = float(dirs[h])
            rad = math.radians(wd)
            series.append({
                "h": h,
                "wind_speed_ms": min(max(ws, 0.5), 30.0),
                "wind_dir_deg": wd,
                "wind_x": ws * math.sin(rad),
                "wind_y": ws * math.cos(rad),
                "source": "open-meteo-cache",
            })
        if not series:
            raise RuntimeError("Wind cache present but unusable")
        return series

    def get_ocean_currents(self, lat: float, lon: float, time_utc: Optional[str] = None) -> dict[str, Any]:
        # Cache keyed on 0.1° grid cell — CMEMS open_dataset is expensive (~25s)
        cache_key = f"currents_{round(lat, 1):.1f}_{round(lon, 1):.1f}".replace("-", "m")
        cache_path = self._path(f"{cache_key}.json")
        ttl = 2 * 3600  # 2 hours
        stale_cache: dict[str, Any] | None = None
        if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < ttl:
            try:
                return json.loads(cache_path.read_text())
            except Exception:
                pass
        elif cache_path.exists():
            try:
                stale_cache = json.loads(cache_path.read_text())
            except Exception:
                stale_cache = None

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fetch_current_point, lat, lon)
                ocean = future.result(timeout=config.EXTERNAL_DATA_TIMEOUT_S)
        except concurrent.futures.TimeoutError as exc:
            if stale_cache:
                stale_cache["source"] = f'{stale_cache.get("source", "cmems-cache")}-stale'
                return stale_cache
            raise RuntimeError("Timed out while fetching real ocean current data") from exc
        if ocean:
            speed = float(ocean.get("current_speed_ms", 0.0))
            direction = math.radians(float(ocean.get("current_dir_deg", 0.0)))
            result = {
                "u_ms": round(speed * math.sin(direction), 4),
                "v_ms": round(speed * math.cos(direction), 4),
                "source": ocean.get("source", "cmems-current"),
            }
        else:
            if stale_cache:
                stale_cache["source"] = f'{stale_cache.get("source", "cmems-cache")}-stale'
                return stale_cache
            raise RuntimeError("Real ocean current data unavailable")

        try:
            cache_path.write_text(json.dumps(result))
        except Exception:
            pass
        return result

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in self.cache_dir.glob("*.json"):
            age_h = (time.time() - f.stat().st_mtime) / 3600
            result[f.stem] = {"age_hours": round(age_h, 1), "stale": age_h > 48}
        return result


if __name__ == "__main__":
    cm = CacheManager()
    wind = cm.get_wind(35.5, 18.0)
    print("CacheManager self-test OK:", wind)
    print("Cache status:", cm.status())
