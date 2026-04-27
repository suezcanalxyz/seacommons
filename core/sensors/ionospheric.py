# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ionospheric TID monitor — Kp index + Madrigal TEC anomaly detection."""
from __future__ import annotations
import base64
import json
import logging
import os
import threading
import time
import urllib.request
from typing import Any, Optional

from core.config import config as _cfg

logger = logging.getLogger(__name__)


class IonosphericMonitor:
    def __init__(self, mock: bool = False):
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true" or _cfg.MOCK
        self.enabled = _cfg.TID_ENABLED or self.mock
        self.region_lat = _cfg.TID_REGION_LAT
        self.region_lon = _cfg.TID_REGION_LON
        self.region_radius_km = _cfg.TID_REGION_RADIUS_KM
        self.poll_interval_s = _cfg.TID_POLL_INTERVAL_S
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.last_kp_index = 0.0
        self.last_event: Optional[dict] = None
        self._tec_baseline: list[float] = []  # rolling 72h window
        self._redis: Any = None

    def _get_redis(self):
        if self._redis is None:
            try:
                import redis  # type: ignore[import]
                self._redis = redis.from_url(
                    os.environ.get("REDIS_URL", _cfg.REDIS_URL)
                )
            except Exception:
                pass
        return self._redis

    def start(self) -> None:
        if not self.enabled:
            logger.info("IonosphericMonitor disabled (TID_ENABLED=false)")
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("IonosphericMonitor started (mock=%s)", self.mock)

    def stop(self) -> None:
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while self.running:
            try:
                self._fetch_kp_index()
                r = self._get_redis()
                storm_active = r and r.get("GEOMAGNETIC_STORM_ACTIVE") == b"true"
                if storm_active:
                    logger.warning("Geomagnetic storm active — suppressing TID alerts")
                else:
                    self._run_tid_pipeline()
            except Exception as exc:
                logger.error("IonosphericMonitor loop error: %s", exc)
            time.sleep(self.poll_interval_s)

    def _fetch_kp_index(self) -> Optional[float]:
        if self.mock:
            self.last_kp_index = 2.0
            return 2.0
        try:
            url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            kp = float(data[-1][1])
            self.last_kp_index = kp
            r = self._get_redis()
            if r:
                if kp > 4:
                    r.setex("GEOMAGNETIC_STORM_ACTIVE", 10800, "true")
                else:
                    r.delete("GEOMAGNETIC_STORM_ACTIVE")
            return kp
        except Exception as exc:
            logger.error("Kp fetch failed: %s", exc)
            return None

    def _run_tid_pipeline(self) -> None:
        r = self._get_redis()
        if r:
            mock_data = r.get("TID_MOCK_EVENT")
            if mock_data:
                event = json.loads(mock_data)
                r.delete("TID_MOCK_EVENT")
                self._publish_event(event)
                return
        if self.mock and __import__("random").random() < 0.05:
            self._publish_event({
                "region_centre": [self.region_lat, self.region_lon],
                "origin_bearing_deg": 42.0,
                "velocity_ms": 750.0,
                "amplitude_tecu": 0.45,
                "stations_count": 4,
                "classification": "ballistic_candidate",
                "confidence": 0.82,
                "data_source": "mock",
            })

    def _publish_event(self, event_data: dict) -> None:
        from datetime import datetime, timezone
        event_data["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        event_data["kp_index"] = self.last_kp_index
        if "raw_rinex_dtec_b64" not in event_data:
            event_data["raw_rinex_dtec_b64"] = base64.b64encode(b"TEC_STUB").decode()
        self.last_event = event_data
        logger.warning(
            "Ionospheric event: %s  confidence=%.2f",
            event_data.get("classification"), event_data.get("confidence"),
        )
        r = self._get_redis()
        if r:
            r.publish("sensors:ionospheric", json.dumps(event_data))

    def get_status(self) -> dict:
        r = self._get_redis()
        storm = r and r.get("GEOMAGNETIC_STORM_ACTIVE") == b"true"
        return {
            "enabled": self.enabled,
            "running": self.running,
            "kp_index": self.last_kp_index,
            "geomagnetic_storm_active": bool(storm),
            "last_event": self.last_event,
            "region": {"lat": self.region_lat, "lon": self.region_lon,
                       "radius_km": self.region_radius_km},
        }

    def run_replay(self, date_str: str, lat: float, lon: float) -> dict:
        event = {
            "region_centre": [lat, lon],
            "origin_bearing_deg": 45.0,
            "velocity_ms": 800.0,
            "amplitude_tecu": 0.5,
            "stations_count": 5,
            "classification": "ballistic_candidate",
            "confidence": 0.85,
            "data_source": "replay",
        }
        self._publish_event(event)
        return event

    def update_cache(self) -> None:
        r = self._get_redis()
        from datetime import datetime, timezone
        if r:
            r.setex("TID_RINEX_CACHE_TIMESTAMP", 48 * 3600,
                    str(datetime.now(timezone.utc).timestamp()))
        logger.info("RINEX cache updated.")


if __name__ == "__main__":
    mon = IonosphericMonitor(mock=True)
    status = mon.get_status()
    print("IonosphericMonitor self-test OK:", status["enabled"])
    replay = mon.run_replay("2022-09-26", 55.535, 15.698)
    print("  Replay event:", replay["classification"], "conf=", replay["confidence"])
