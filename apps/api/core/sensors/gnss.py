# SPDX-License-Identifier: AGPL-3.0-or-later
"""GNSS spoofing monitor — GPSJam heatmap + NMEA anomaly detection."""
from __future__ import annotations
import json
import logging
import math
import os
import threading
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel

from core.config import config as _cfg

logger = logging.getLogger(__name__)
_CACHE_FILE = Path.home() / ".suezcanal" / "cache" / "gpsjam.json"


class GNSSAnomalyEvent(BaseModel):
    event_id: str
    timestamp_utc: str
    anomaly_type: str  # spoofing_zone | position_jump | impossible_speed | altitude_anomaly
    lat: float
    lon: float
    description: str
    confidence: float = 0.7
    source: str = "gnss"


class GNSSMonitor:
    def __init__(self, mock: bool = False, on_anomaly: Optional[Callable] = None):
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true" or _cfg.MOCK
        self._on_anomaly = on_anomaly
        self._gpsjam_features: list[dict] = []
        self._last_position: Optional[tuple[float, float, float]] = None  # lat,lon,t
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not _cfg.GNSS_ENABLED and not self.mock:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def is_spoofing_active(self, lat: float, lon: float) -> bool:
        """Return True if GPSJam reports interference near this position."""
        for feat in self._gpsjam_features:
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [])
            if geom.get("type") == "Point" and len(coords) >= 2:
                dlat = lat - coords[1]
                dlon = lon - coords[0]
                dist = math.sqrt(dlat**2 + dlon**2) * 111
                if dist < 500:  # within 500 km
                    return True
        return False

    def _loop(self) -> None:
        self._fetch_gpsjam()
        while self._running:
            time.sleep(6 * 3600)  # refresh every 6h
            self._fetch_gpsjam()

    def _fetch_gpsjam(self) -> None:
        try:
            with urllib.request.urlopen(_cfg.GPSJAM_URL, timeout=15) as resp:
                data = json.loads(resp.read())
            self._gpsjam_features = data.get("features", [])
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_FILE.write_text(json.dumps(data))
            logger.info("GPSJam: %d features loaded", len(self._gpsjam_features))
        except Exception as exc:
            logger.warning("GPSJam fetch failed (%s); using cache", exc)
            if _CACHE_FILE.exists():
                try:
                    data = json.loads(_CACHE_FILE.read_text())
                    self._gpsjam_features = data.get("features", [])
                except Exception:
                    pass

    def check_nmea_position(self, lat: float, lon: float) -> None:
        """Call this from NMEAParser on each GGA sentence."""
        from datetime import datetime, timezone
        now = time.monotonic()
        if self._last_position is not None:
            plat, plon, pts = self._last_position
            dt = now - pts
            dist_nm = math.sqrt((lat - plat)**2 + (lon - plon)**2) * 60  # approx
            if dt > 0:
                speed_kts = dist_nm / (dt / 3600)
                if dist_nm > 0.1 and dt < 1.0:
                    self._emit("position_jump", lat, lon,
                               f"Position jumped {dist_nm:.2f} nm in {dt:.1f}s", 0.85)
                elif speed_kts > 100:
                    self._emit("impossible_speed", lat, lon,
                               f"Speed {speed_kts:.0f} kts — physically impossible", 0.80)
        self._last_position = (lat, lon, now)
        if self.is_spoofing_active(lat, lon):
            self._emit("spoofing_zone", lat, lon, "Position within active GPSJam interference zone", 0.75)

    def _emit(self, anomaly_type, lat, lon, description, confidence) -> None:
        from datetime import datetime, timezone
        event = GNSSAnomalyEvent(
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            anomaly_type=anomaly_type,
            lat=lat, lon=lon,
            description=description,
            confidence=confidence,
        )
        if self._on_anomaly:
            self._on_anomaly(event)
        try:
            import redis  # type: ignore[import]
            r = redis.from_url(os.environ.get("REDIS_URL", _cfg.REDIS_URL))
            r.publish("gnss:anomalies", event.model_dump_json())
        except Exception:
            pass


if __name__ == "__main__":
    events: list[GNSSAnomalyEvent] = []
    mon = GNSSMonitor(mock=True, on_anomaly=events.append)
    # Simulate position jump
    mon._last_position = (35.500, 14.000, time.monotonic() - 0.3)
    mon.check_nmea_position(35.510, 14.010)
    print(f"GNSSMonitor self-test OK: {len(events)} events")
    if events:
        print(f"  {events[0].anomaly_type}: {events[0].description}")
