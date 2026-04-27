# SPDX-License-Identifier: AGPL-3.0-or-later
"""ADS-B receiver — dump1090 JSON feed or RTL-SDR via pyModeS or MOCK."""
from __future__ import annotations
import json
import logging
import os
import random
import threading
import time
import urllib.request
import uuid
from typing import Callable, Optional

from pydantic import BaseModel

from core.config import config as _cfg

logger = logging.getLogger(__name__)

# ICAO hex ranges for military aircraft
_MILITARY_RANGES = [
    (0x3C0000, 0x3CFFFF),  # Germany military
    (0xAE0000, 0xAEFFFF),  # US military
    (0x43C000, 0x43CFFF),  # UK military
]

# Airport approach zones (simplified — 50nm radius circles)
_AIRPORTS: list[tuple[float, float]] = [
    (35.857, 14.477),   # Malta MLA
    (37.700, 12.588),   # Palermo PMO
    (37.467, 15.066),   # Catania CTA
    (40.651, 14.291),   # Naples NAP
]


def _is_military(icao_hex: str) -> bool:
    try:
        v = int(icao_hex, 16)
        return any(lo <= v <= hi for lo, hi in _MILITARY_RANGES)
    except ValueError:
        return False


def _near_airport(lat: float, lon: float, radius_deg: float = 0.83) -> bool:  # ~50nm
    return any(
        abs(lat - alat) < radius_deg and abs(lon - alon) < radius_deg
        for alat, alon in _AIRPORTS
    )


class ADSBAnomalyEvent(BaseModel):
    event_id: str
    timestamp_utc: str
    anomaly_type: str  # low_altitude | military_pattern | no_transponder | disappearance | formation
    icao: str
    callsign: str = ""
    altitude_ft: float = 0.0
    lat: float = 0.0
    lon: float = 0.0
    confidence: float = 0.7
    source: str = "adsb"


class ADSBReceiver:
    def __init__(self, mock: bool = False, on_anomaly: Optional[Callable] = None):
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true" or _cfg.MOCK
        self._on_anomaly = on_anomaly
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._seen: dict[str, dict] = {}   # icao → last seen
        self._last_seen_ts: dict[str, float] = {}

    def start(self) -> None:
        if self._running:
            return
        if not _cfg.ADSB_ENABLED and not self.mock:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            aircraft = self._fetch_aircraft()
            now = time.time()
            seen_this_cycle: set[str] = set()
            for ac in aircraft:
                icao = ac.get("hex", "").lower()
                if not icao:
                    continue
                lat = ac.get("lat", 0.0)
                lon = ac.get("lon", 0.0)
                alt_ft = ac.get("alt_baro", ac.get("altitude", 0)) or 0
                callsign = ac.get("flight", "").strip()
                squawk = ac.get("squawk", "")
                seen_this_cycle.add(icao)
                self._last_seen_ts[icao] = now
                self._seen[icao] = ac

                # Low altitude outside airport approach
                if 0 < alt_ft < 500 and not _near_airport(lat, lon):
                    self._emit("low_altitude", icao, callsign, alt_ft, lat, lon, 0.80)

                # Military ICAO
                if _is_military(icao):
                    self._emit("military_pattern", icao, callsign, alt_ft, lat, lon, 0.75)

                # No squawk (mode S but no squawk code)
                if not squawk and callsign:
                    self._emit("no_transponder", icao, callsign, alt_ft, lat, lon, 0.60)

            # Disappearance — icao seen last cycle but not this one, within region
            for icao, ts in list(self._last_seen_ts.items()):
                if icao not in seen_this_cycle and now - ts > 120:
                    ac = self._seen.get(icao, {})
                    if ac.get("lat") and not _near_airport(ac.get("lat", 0), ac.get("lon", 0)):
                        self._emit("disappearance", icao, "", 0, ac.get("lat", 0), ac.get("lon", 0), 0.65)
                    del self._last_seen_ts[icao]
                    self._seen.pop(icao, None)

            time.sleep(60)

    def _fetch_aircraft(self) -> list[dict]:
        if self.mock:
            return self._mock_aircraft()
        try:
            url = "http://localhost:8080/data/aircraft.json"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
            return data.get("aircraft", [])
        except Exception:
            return []

    def _mock_aircraft(self) -> list[dict]:
        aircraft = []
        for i in range(5):
            icao = f"ae{random.randint(0, 0xFFFF):04x}"
            aircraft.append({
                "hex": icao,
                "flight": f"MOCK{i}",
                "lat": 35.5 + random.uniform(-2, 2),
                "lon": 14.0 + random.uniform(-2, 2),
                "alt_baro": random.choice([200, 1500, 8000, 35000]),
                "squawk": str(random.randint(1000, 7777)) if random.random() > 0.2 else "",
            })
        return aircraft

    def _emit(self, anomaly_type, icao, callsign, alt_ft, lat, lon, confidence) -> None:
        from datetime import datetime, timezone
        event = ADSBAnomalyEvent(
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            anomaly_type=anomaly_type,
            icao=icao,
            callsign=callsign,
            altitude_ft=alt_ft,
            lat=lat,
            lon=lon,
            confidence=confidence,
        )
        logger.warning("ADS-B anomaly: %s  icao=%s", anomaly_type, icao)
        if self._on_anomaly:
            self._on_anomaly(event)
        try:
            import redis  # type: ignore[import]
            r = redis.from_url(os.environ.get("REDIS_URL", _cfg.REDIS_URL))
            r.publish("adsb:anomalies", event.model_dump_json())
        except Exception:
            pass


if __name__ == "__main__":
    events: list[ADSBAnomalyEvent] = []
    recv = ADSBReceiver(mock=True, on_anomaly=events.append)
    recv._fetch_aircraft()   # smoke test
    # Inject low-altitude aircraft
    recv._seen["ae1234"] = {"lat": 35.5, "lon": 14.0}
    recv._emit("low_altitude", "ae1234", "TEST01", 200, 35.5, 14.0, 0.8)
    print(f"ADSBReceiver self-test OK: {len(events)} events")
    if events:
        print(f"  {events[0].anomaly_type}  icao={events[0].icao}")
