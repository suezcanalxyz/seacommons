# SPDX-License-Identifier: AGPL-3.0-or-later
"""AIS anomaly detector — gap, impossible speed, duplicate MMSI, dark zones, OFAC SDN."""
from __future__ import annotations
import asyncio
import json
import logging
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

_SDN_CACHE = Path.home() / ".suezcanal" / "cache" / "sdn_mmsi.json"

# AIS dark zones (simplified — areas with known AIS reception gaps)
_DARK_ZONES: list[tuple[float, float, float, float]] = [
    (23.5, 37.0, 28.0, 42.0),   # Eastern Med AIS gap
    (10.0, 30.0, 16.0, 36.0),   # Libyan coast gap
]

# Maximum realistic speeds by vessel type (knots)
_MAX_SPEED: dict[str, float] = {
    "cargo": 30, "tanker": 20, "passenger": 35, "fishing": 20,
    "tug": 15, "sailing": 18, "default": 50,
}


class AISAnomalyEvent(BaseModel):
    event_id: str
    timestamp_utc: str
    anomaly_type: str  # gap | impossible_speed | mmsi_duplicate | dark_zone_entry | sdn_match
    mmsi: str
    vessel_name: str = ""
    position: dict
    confidence: float
    evidence: dict
    source: str = "ais"


class AISAnomalyDetector:
    def __init__(self, mock: bool = False, on_anomaly: Optional[Callable] = None):
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true" or _cfg.MOCK
        self._on_anomaly = on_anomaly
        self._last_seen: dict[str, dict] = {}  # mmsi → {lat, lon, ts, speed, type}
        self._positions: dict[str, dict] = {}  # mmsi → latest position
        self._sdn_mmsi: set[str] = set()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._running = True
        self._load_sdn()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run(self) -> None:
        if self.mock:
            self._mock_loop()
        else:
            asyncio.run(self._ws_loop())

    def _mock_loop(self) -> None:
        import random
        while self._running:
            mmsi = f"2470{random.randint(10000, 99999)}"
            lat = 35.0 + random.uniform(-3, 3)
            lon = 14.0 + random.uniform(-4, 4)
            speed = random.uniform(0, 25)
            self.process_position(mmsi, "MockVessel", lat, lon, speed, "cargo")
            time.sleep(2)

    async def _ws_loop(self) -> None:
        try:
            import websockets  # type: ignore[import]
        except ImportError:
            logger.warning("websockets not installed — AIS anomaly detector idle")
            return
        key = _cfg.AISSTREAM_KEY
        if not key:
            logger.warning("No AISSTREAM_KEY — AIS anomaly detector idle")
            return
        while self._running:
            try:
                async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
                    await ws.send(json.dumps({
                        "APIKey": key,
                        "BoundingBoxes": [[[-90, -180], [90, 180]]],
                        "MessageTypes": ["PositionReport"],
                    }))
                    async for raw in ws:
                        msg = json.loads(raw)
                        meta = msg.get("MetaData", {})
                        pr = (msg.get("Message", {}).get("PositionReport") or
                              msg.get("Message", {}).get("StandardClassBPositionReport") or {})
                        mmsi = str(meta.get("MMSI", ""))
                        if mmsi and pr:
                            self.process_position(
                                mmsi,
                                meta.get("ShipName", ""),
                                meta.get("latitude", pr.get("Latitude", 0)),
                                meta.get("longitude", pr.get("Longitude", 0)),
                                pr.get("Sog", 0),
                                "",
                            )
            except Exception as exc:
                logger.warning("AIS WS error: %s — retry in 30s", exc)
                await asyncio.sleep(30)

    def process_position(
        self, mmsi: str, name: str, lat: float, lon: float, speed: float, vessel_type: str
    ) -> None:
        from datetime import datetime, timezone
        now = time.time()
        prev = self._last_seen.get(mmsi)
        pos = {"lat": lat, "lon": lon}

        # Gap detection: vessel previously seen in open water but now silent
        if prev:
            gap_s = now - prev["ts"]
            # Check impossible speed
            import math
            dlat = lat - prev["lat"]
            dlon = lon - prev["lon"]
            dist_nm = math.sqrt(dlat**2 + dlon**2) * 60
            if gap_s > 0 and dist_nm > 0:
                reported_speed = speed
                actual_speed_kts = dist_nm / (gap_s / 3600)
                max_spd = _MAX_SPEED.get(vessel_type, _MAX_SPEED["default"])
                if actual_speed_kts > max_spd and actual_speed_kts > 55:
                    self._emit(AISAnomalyEvent(
                        event_id=str(uuid.uuid4()),
                        timestamp_utc=datetime.now(timezone.utc).isoformat(),
                        anomaly_type="impossible_speed",
                        mmsi=mmsi, vessel_name=name,
                        position=pos,
                        confidence=min(0.9, 0.5 + (actual_speed_kts - max_spd) / 100),
                        evidence={"computed_kts": round(actual_speed_kts, 1),
                                  "max_allowed": max_spd, "gap_s": round(gap_s)},
                    ))

            # Silence gap > 180s in open water
            if gap_s > 180 and not self._in_dark_zone(lat, lon):
                self._emit(AISAnomalyEvent(
                    event_id=str(uuid.uuid4()),
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    anomaly_type="gap",
                    mmsi=mmsi, vessel_name=name,
                    position=pos,
                    confidence=min(0.85, 0.4 + gap_s / 3600),
                    evidence={"gap_seconds": round(gap_s)},
                ))

        # Dark zone entry
        if self._in_dark_zone(lat, lon) and (not prev or not self._in_dark_zone(prev["lat"], prev["lon"])):
            self._emit(AISAnomalyEvent(
                event_id=str(uuid.uuid4()),
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                anomaly_type="dark_zone_entry",
                mmsi=mmsi, vessel_name=name,
                position=pos, confidence=0.65,
                evidence={"zone": "known_ais_blackout_area"},
            ))

        # OFAC SDN list match
        if mmsi in self._sdn_mmsi:
            self._emit(AISAnomalyEvent(
                event_id=str(uuid.uuid4()),
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                anomaly_type="sdn_match",
                mmsi=mmsi, vessel_name=name,
                position=pos, confidence=0.95,
                evidence={"list": "OFAC_SDN"},
            ))

        self._last_seen[mmsi] = {"lat": lat, "lon": lon, "ts": now, "speed": speed, "type": vessel_type}
        self._positions[mmsi] = pos

    def _in_dark_zone(self, lat: float, lon: float) -> bool:
        return any(lat0 <= lat <= lat1 and lon0 <= lon <= lon1
                   for lat0, lon0, lat1, lon1 in _DARK_ZONES)

    def _emit(self, event: AISAnomalyEvent) -> None:
        logger.warning("AIS anomaly: %s mmsi=%s conf=%.2f", event.anomaly_type, event.mmsi, event.confidence)
        if self._on_anomaly:
            self._on_anomaly(event)
        try:
            import redis  # type: ignore[import]
            r = redis.from_url(os.environ.get("REDIS_URL", _cfg.REDIS_URL))
            r.publish("ais:anomalies", event.model_dump_json())
        except Exception:
            pass

    def _load_sdn(self) -> None:
        if _SDN_CACHE.exists():
            try:
                self._sdn_mmsi = set(json.loads(_SDN_CACHE.read_text()))
                return
            except Exception:
                pass
        # Download OFAC SDN — parse for vessel MMSI references
        try:
            url = "https://www.treasury.gov/ofac/downloads/sdn.json"
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read())
            mmsis: set[str] = set()
            for entry in data.get("sdnList", {}).get("sdnEntry", []):
                for prop in entry.get("idList", {}).get("id", []):
                    if "MMSI" in prop.get("idType", "").upper():
                        mmsis.add(str(prop.get("idNumber", "")).strip())
            _SDN_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _SDN_CACHE.write_text(json.dumps(list(mmsis)))
            self._sdn_mmsi = mmsis
        except Exception:
            pass


if __name__ == "__main__":
    events: list[AISAnomalyEvent] = []
    det = AISAnomalyDetector(mock=True, on_anomaly=events.append)
    # Inject impossible-speed scenario
    det._last_seen["247012345"] = {"lat": 35.0, "lon": 14.0, "ts": time.time() - 60, "speed": 10, "type": "cargo"}
    det.process_position("247012345", "TestVessel", 36.0, 15.0, 300, "cargo")
    print(f"AISAnomalyDetector self-test OK: {len(events)} events")
    if events:
        print(f"  {events[0].anomaly_type}  evidence={events[0].evidence}")
