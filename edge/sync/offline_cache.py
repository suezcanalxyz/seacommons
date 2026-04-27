# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline cache — downloads all assets needed for disconnected operation."""
from __future__ import annotations
import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
CACHE_DIR = Path.home() / ".suezcanal" / "cache"
TTL_S = 48 * 3600

_ASSETS = ["wind_cache", "acled", "sdn_mmsi", "gpsjam", "region"]


class OfflineCache:
    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.cache_dir / f"{name}.json"

    def is_stale(self, asset: str) -> bool:
        p = self._path(asset)
        if not p.exists():
            return True
        return (time.time() - p.stat().st_mtime) > TTL_S

    def update(self, region_lat: float, region_lon: float, radius_km: float = 500) -> None:
        """Download all regional assets."""
        self._update_wind(region_lat, region_lon)
        self._update_gpsjam()
        self._update_sdn()
        self._update_acled(region_lat, region_lon)
        logger.info("Offline cache updated for (%.2f, %.2f) r=%.0fkm", region_lat, region_lon, radius_km)

    def _update_wind(self, lat: float, lon: float) -> None:
        try:
            url = (f"https://api.open-meteo.com/v1/forecast"
                   f"?latitude={lat:.3f}&longitude={lon:.3f}"
                   f"&hourly=wind_speed_10m,wind_direction_10m&wind_speed_unit=ms&forecast_days=2")
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
            self._path("wind_cache").write_text(json.dumps({"lat": lat, "lon": lon, "data": data, "ts": time.time()}))
        except Exception as exc:
            logger.warning("wind update failed: %s", exc)

    def _update_gpsjam(self) -> None:
        try:
            from core.config import config
            with urllib.request.urlopen(config.GPSJAM_URL, timeout=15) as r:
                data = json.loads(r.read())
            self._path("gpsjam").write_text(json.dumps(data))
        except Exception as exc:
            logger.warning("gpsjam update failed: %s", exc)

    def _update_sdn(self) -> None:
        if not self.is_stale("sdn_mmsi"):
            return
        try:
            url = "https://www.treasury.gov/ofac/downloads/sdn.json"
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.loads(r.read())
            mmsis = []
            for entry in data.get("sdnList", {}).get("sdnEntry", []):
                for prop in entry.get("idList", {}).get("id", []):
                    if "MMSI" in prop.get("idType", "").upper():
                        mmsis.append(str(prop.get("idNumber", "")))
            self._path("sdn_mmsi").write_text(json.dumps(mmsis))
        except Exception as exc:
            logger.warning("SDN update failed: %s", exc)

    def _update_acled(self, lat: float, lon: float) -> None:
        from core.config import config
        if not config.ACLED_KEY:
            return
        try:
            url = (f"https://api.acleddata.com/acled/read?key={config.ACLED_KEY}"
                   f"&latitude={lat}&longitude={lon}&radius=1000&limit=500&fields=latitude,longitude,event_type,event_date")
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read())
            self._path("acled").write_text(json.dumps(data.get("data", [])))
        except Exception as exc:
            logger.warning("ACLED update failed: %s", exc)

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for asset in _ASSETS:
            p = self._path(asset)
            if p.exists():
                age_h = (time.time() - p.stat().st_mtime) / 3600
                result[asset] = {"age_hours": round(age_h, 1), "stale": age_h > 48}
            else:
                result[asset] = {"age_hours": None, "stale": True}
        return result


if __name__ == "__main__":
    oc = OfflineCache()
    print("OfflineCache self-test OK")
    print("Status:", json.dumps(oc.status(), indent=2))
