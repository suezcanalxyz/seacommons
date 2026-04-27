# SPDX-License-Identifier: AGPL-3.0-or-later
"""Traffic anomaly detector — ADS-B + ACLED conflict cross-reference."""
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
_ACLED_CACHE = Path.home() / ".suezcanal" / "cache" / "acled.json"


class TrafficAnomalyEvent(BaseModel):
    event_id: str
    timestamp_utc: str
    anomaly_type: str  # low_altitude | military_pattern | no_transponder | formation_flight
    icao: str
    callsign: str = ""
    altitude_ft: float = 0.0
    lat: float = 0.0
    lon: float = 0.0
    confidence: float
    acled_nearby: list[dict] = []
    source: str = "traffic"


class TrafficAnomalyDetector:
    def __init__(self, mock: bool = False, on_anomaly: Optional[Callable] = None):
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true" or _cfg.MOCK
        self._on_anomaly = on_anomaly
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._aircraft: dict[str, dict] = {}
        self._acled: list[dict] = []

    def start(self) -> None:
        if not _cfg.ADSB_ENABLED and not self.mock:
            return
        self._load_acled()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            aircraft = self._fetch_aircraft()
            self._analyze(aircraft)
            time.sleep(60)

    def _fetch_aircraft(self) -> list[dict]:
        if self.mock:
            import random
            return [{
                "hex": f"ae{random.randint(0,0xFFFF):04x}",
                "flight": f"TEST{i}",
                "lat": 35.0 + random.uniform(-2, 2),
                "lon": 14.0 + random.uniform(-2, 2),
                "alt_baro": random.choice([200, 400, 2000, 35000]),
                "squawk": str(random.randint(1000, 7777)) if random.random() > 0.15 else "",
                "track": random.uniform(0, 360),
            } for i in range(6)]
        try:
            with urllib.request.urlopen("http://localhost:8080/data/aircraft.json", timeout=5) as r:
                return json.loads(r.read()).get("aircraft", [])
        except Exception:
            return []

    def _analyze(self, aircraft: list[dict]) -> None:
        for ac in aircraft:
            icao = ac.get("hex", "").lower()
            lat = ac.get("lat", 0.0) or 0.0
            lon = ac.get("lon", 0.0) or 0.0
            alt_ft = ac.get("alt_baro", 0) or 0
            callsign = ac.get("flight", "").strip()
            track = ac.get("track", 0.0) or 0.0
            self._aircraft[icao] = ac

            # Low altitude detection
            if 0 < alt_ft < 500:
                nearby_acled = self._nearby_acled(lat, lon, radius_km=200)
                self._emit("low_altitude", icao, callsign, alt_ft, lat, lon,
                           0.75 + min(0.15, len(nearby_acled) * 0.03), nearby_acled)

            # Military ICAO hex range
            try:
                v = int(icao, 16)
                if 0x3C0000 <= v <= 0x3CFFFF or 0xAE0000 <= v <= 0xAEFFFF:
                    self._emit("military_pattern", icao, callsign, alt_ft, lat, lon, 0.75, [])
            except ValueError:
                pass

            # No transponder squawk
            if not ac.get("squawk") and callsign and alt_ft < 5000:
                self._emit("no_transponder", icao, callsign, alt_ft, lat, lon, 0.60, [])

        # Formation flight: 2+ aircraft within 1nm same heading ±5deg
        acs = list(self._aircraft.values())
        for i, a in enumerate(acs):
            for b in acs[i+1:]:
                la, loa = a.get("lat", 0.0) or 0, a.get("lon", 0.0) or 0
                lb, lob = b.get("lat", 0.0) or 0, b.get("lon", 0.0) or 0
                dist_nm = math.sqrt((la - lb)**2 + (loa - lob)**2) * 60
                ta = a.get("track", 0.0) or 0
                tb = b.get("track", 0.0) or 0
                if dist_nm < 1.0 and abs(ta - tb) < 5:
                    self._emit("formation_flight",
                               a.get("hex", ""), a.get("flight", "").strip(),
                               a.get("alt_baro", 0), la, loa, 0.70, [])

    def _nearby_acled(self, lat: float, lon: float, radius_km: float) -> list[dict]:
        from datetime import datetime, timezone
        result = []
        for event in self._acled:
            elat = float(event.get("latitude", 0))
            elon = float(event.get("longitude", 0))
            dist = math.sqrt((lat - elat)**2 + (lon - elon)**2) * 111
            if dist <= radius_km:
                result.append(event)
        return result[:5]

    def _emit(self, anomaly_type, icao, callsign, alt_ft, lat, lon, confidence, acled) -> None:
        from datetime import datetime, timezone
        event = TrafficAnomalyEvent(
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            anomaly_type=anomaly_type,
            icao=icao, callsign=callsign,
            altitude_ft=alt_ft, lat=lat, lon=lon,
            confidence=confidence, acled_nearby=acled,
        )
        logger.warning("Traffic anomaly: %s icao=%s conf=%.2f", anomaly_type, icao, confidence)
        if self._on_anomaly:
            self._on_anomaly(event)
        try:
            import redis  # type: ignore[import]
            r = redis.from_url(os.environ.get("REDIS_URL", _cfg.REDIS_URL))
            r.publish("traffic:anomalies", event.model_dump_json())
        except Exception:
            pass

    def _load_acled(self) -> None:
        if _ACLED_CACHE.exists():
            try:
                self._acled = json.loads(_ACLED_CACHE.read_text())
                return
            except Exception:
                pass
        if not _cfg.ACLED_KEY:
            return
        try:
            url = (f"https://api.acleddata.com/acled/read?key={_cfg.ACLED_KEY}"
                   f"&region=11&limit=500&fields=latitude,longitude,event_type,event_date")
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read())
            self._acled = data.get("data", [])
            _ACLED_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _ACLED_CACHE.write_text(json.dumps(self._acled))
        except Exception as exc:
            logger.warning("ACLED load failed: %s", exc)


if __name__ == "__main__":
    events: list[TrafficAnomalyEvent] = []
    det = TrafficAnomalyDetector(mock=True, on_anomaly=events.append)
    det._emit("low_altitude", "ae1234", "TEST", 250, 35.5, 14.0, 0.80, [])
    print(f"TrafficAnomalyDetector self-test OK: {len(events)} events")
    if events:
        print(f"  {events[0].anomaly_type}  alt={events[0].altitude_ft}ft")
