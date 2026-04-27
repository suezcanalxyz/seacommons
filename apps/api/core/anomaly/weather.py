# SPDX-License-Identifier: AGPL-3.0-or-later
"""Weather anomaly detector — Open-Meteo SAR thresholds."""
from __future__ import annotations
import json
import logging
import os
import threading
import time
import urllib.request
import uuid
from typing import Callable, Optional

from pydantic import BaseModel

from core.config import config as _cfg

logger = logging.getLogger(__name__)

# SAR operational thresholds
_SAR_WIND_KTS = 25.0
_SAR_WAVE_M = 2.5
_STORM_WIND_KTS = 40.0
_LOW_VIS_M = 500.0


class WeatherAlertEvent(BaseModel):
    event_id: str
    timestamp_utc: str
    alert_type: str   # SAR_CONDITIONS | STORM_CONDITIONS | LOW_VISIBILITY
    lat: float
    lon: float
    wind_kts: float
    wave_height_m: float = 0.0
    visibility_m: float = 9999.0
    confidence: float = 0.90
    source: str = "weather"


class WeatherAnomalyDetector:
    def __init__(self, mock: bool = False, on_alert: Optional[Callable] = None):
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true" or _cfg.MOCK
        self._on_alert = on_alert
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._active_regions: list[tuple[float, float]] = [
            (35.5, 14.0),   # Central Mediterranean
            (36.5, 12.5),   # Sicily Channel
        ]

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def add_distress_region(self, lat: float, lon: float) -> None:
        if (lat, lon) not in self._active_regions:
            self._active_regions.append((lat, lon))

    def _loop(self) -> None:
        while self._running:
            for lat, lon in list(self._active_regions):
                self._check(lat, lon)
            time.sleep(3600)

    def _check(self, lat: float, lon: float) -> None:
        if self.mock:
            import random
            wind_ms = random.uniform(3, 20)
            wave_m = random.uniform(0.5, 4.0)
            vis_m = random.uniform(200, 15000)
        else:
            wind_ms, wave_m, vis_m = self._fetch(lat, lon)

        wind_kts = wind_ms * 1.944

        if wind_kts > _STORM_WIND_KTS:
            self._emit("STORM_CONDITIONS", lat, lon, wind_kts, wave_m, vis_m)
        elif wind_kts > _SAR_WIND_KTS and wave_m > _SAR_WAVE_M:
            self._emit("SAR_CONDITIONS", lat, lon, wind_kts, wave_m, vis_m)
        if vis_m < _LOW_VIS_M:
            self._emit("LOW_VISIBILITY", lat, lon, wind_kts, wave_m, vis_m)

    def _fetch(self, lat: float, lon: float) -> tuple[float, float, float]:
        try:
            url = (
                f"{_cfg.OPEN_METEO_BASE}/forecast"
                f"?latitude={lat:.3f}&longitude={lon:.3f}"
                f"&current=wind_speed_10m,wind_gusts_10m,visibility"
                f"&hourly=wave_height&wind_speed_unit=ms&forecast_days=1"
            )
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            wind = data.get("current", {}).get("wind_speed_10m", 5.0)
            vis = data.get("current", {}).get("visibility", 9999)
            waves = data.get("hourly", {}).get("wave_height", [1.0])
            wave = waves[0] if waves else 1.0
            return float(wind), float(wave), float(vis)
        except Exception:
            return 5.0, 1.0, 9999.0

    def _emit(self, alert_type, lat, lon, wind_kts, wave_m, vis_m) -> None:
        from datetime import datetime, timezone
        event = WeatherAlertEvent(
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            alert_type=alert_type,
            lat=lat, lon=lon,
            wind_kts=round(wind_kts, 1),
            wave_height_m=round(wave_m, 1),
            visibility_m=round(vis_m),
        )
        logger.warning("Weather alert: %s @ %.2f,%.2f  wind=%.1fkts", alert_type, lat, lon, wind_kts)
        if self._on_alert:
            self._on_alert(event)
        try:
            import redis  # type: ignore[import]
            r = redis.from_url(os.environ.get("REDIS_URL", _cfg.REDIS_URL))
            r.publish("weather:alerts", event.model_dump_json())
        except Exception:
            pass


if __name__ == "__main__":
    events: list[WeatherAlertEvent] = []
    det = WeatherAnomalyDetector(mock=True, on_alert=events.append)
    # Inject SAR conditions
    det._emit("SAR_CONDITIONS", 35.5, 14.0, 27.0, 3.2, 5000)
    det._emit("STORM_CONDITIONS", 35.5, 14.0, 45.0, 5.0, 2000)
    det._emit("LOW_VISIBILITY", 35.5, 14.0, 10.0, 1.0, 200)
    print(f"WeatherAnomalyDetector self-test OK: {len(events)} events")
    for e in events:
        print(f"  {e.alert_type}  wind={e.wind_kts}kts")
    assert len(events) == 3
    print("All assertions passed.")
