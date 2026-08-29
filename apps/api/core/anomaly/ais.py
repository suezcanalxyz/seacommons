# SPDX-License-Identifier: AGPL-3.0-or-later
"""AIS anomaly detector — gap, impossible speed, duplicate MMSI, dark zones, OFAC SDN."""
from __future__ import annotations
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
        self._last_seen: dict[str, dict] = {}  # mmsi → {lat, lon, ts, speed, type, name}
        self._positions: dict[str, dict] = {}  # mmsi → latest position
        self._sdn_mmsi: set[str] = set()
        self._emitted: dict[tuple[str, str], float] = {}  # (mmsi, type) → last emit
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Attach to the shared AIS feed and run the silence-sweep thread.

        The old _ws_loop opened its own AISStream socket, which conflicts
        with the primary client (one connection per key on the free tier) --
        that is why this detector was never wired in. It now consumes the
        same PositionReports as everything else via a position hook.
        """
        self._running = True
        self._load_sdn()
        try:
            from core.vessels import aisstream

            aisstream.register_position_hook(self._on_feed_position)
        except Exception as exc:
            logger.warning("AISAnomalyDetector: could not attach to AIS feed: %s", exc)
        self._thread = threading.Thread(
            target=self._silence_sweep_loop, daemon=True, name="ais-anomaly-sweep"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _on_feed_position(
        self, mmsi: str, name: str, lat: float, lon: float,
        sog: float | None, nav_status: int | None = None, *_extra,
    ) -> None:
        if self._running:
            self.process_position(mmsi, name, lat, lon, sog or 0.0, "")

    def _silence_sweep_loop(self) -> None:
        """Emit a `gap` for a vessel last seen underway in open water that has
        now been silent past the threshold -- the absence of a message, which
        a per-message hook cannot see on its own."""
        from datetime import datetime, timezone

        while self._running:
            time.sleep(90)
            now = time.time()
            # Bounded memory on the small VM: drop tracks and cooldowns that
            # can no longer produce an event.
            self._last_seen = {
                m: s for m, s in self._last_seen.items() if now - s["ts"] < 12 * 3600
            }
            self._emitted = {
                k: t for k, t in self._emitted.items() if now - t < self._EMIT_COOLDOWN_S * 2
            }
            for mmsi, seen in list(self._last_seen.items()):
                if seen.get("gap_emitted"):
                    continue
                silent_s = now - seen["ts"]
                if silent_s < 900 or silent_s > 6 * 3600:
                    continue
                if seen.get("speed", 0) < 1.0 or self._in_dark_zone(seen["lat"], seen["lon"]):
                    continue
                seen["gap_emitted"] = True
                self._emit(AISAnomalyEvent(
                    event_id=str(uuid.uuid4()),
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    anomaly_type="gap",
                    mmsi=mmsi, vessel_name=seen.get("name", ""),
                    position={"lat": seen["lat"], "lon": seen["lon"]},
                    confidence=min(0.85, 0.4 + silent_s / 7200),
                    evidence={"silent_seconds": round(silent_s), "sweep": True},
                ))

    def process_position(
        self, mmsi: str, name: str, lat: float, lon: float, speed: float, vessel_type: str
    ) -> None:
        from datetime import datetime, timezone
        now = time.time()
        prev = self._last_seen.get(mmsi)
        pos = {"lat": lat, "lon": lon}

        # Impossible speed between two fixes (AIS spoofing / MMSI reuse).
        # Silence "gap" is handled by the sweep loop, not here -- a normal AIS
        # refresh interval routinely exceeds a few minutes.
        if prev:
            gap_s = now - prev["ts"]
            import math
            dlat = lat - prev["lat"]
            dlon = lon - prev["lon"]
            dist_nm = math.sqrt(dlat**2 + dlon**2) * 60
            if gap_s > 0 and dist_nm > 0:
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

        self._last_seen[mmsi] = {
            "lat": lat, "lon": lon, "ts": now, "speed": speed,
            "type": vessel_type, "name": name or self._last_seen.get(mmsi, {}).get("name", ""),
        }
        self._positions[mmsi] = pos

    def _in_dark_zone(self, lat: float, lon: float) -> bool:
        return any(lat0 <= lat <= lat1 and lon0 <= lon <= lon1
                   for lat0, lon0, lat1, lon1 in _DARK_ZONES)

    _EMIT_COOLDOWN_S = 3 * 3600

    def _emit(self, event: AISAnomalyEvent) -> None:
        key = (event.mmsi, event.anomaly_type)
        now = time.time()
        if now - self._emitted.get(key, 0.0) < self._EMIT_COOLDOWN_S:
            return
        self._emitted[key] = now
        logger.warning("AIS anomaly: %s mmsi=%s conf=%.2f", event.anomaly_type, event.mmsi, event.confidence)
        if self._on_anomaly:
            self._on_anomaly(event)
        self._to_intel_event(event)
        try:
            import redis  # type: ignore[import]
            r = redis.from_url(os.environ.get("REDIS_URL", _cfg.REDIS_URL))
            r.publish("ais:anomalies", event.model_dump_json())
        except Exception:
            pass

    @staticmethod
    def _to_intel_event(event: AISAnomalyEvent) -> None:
        """An AIS anomaly is an operator-only analysis signal -- never a
        public distress. Persist it so it shows in the intel feed."""
        try:
            from core.intel.store import IntelEvent, intel_store

            label = event.anomaly_type.replace("_", " ")
            intel_store.add(
                IntelEvent(
                    id=f"aisanom:{event.mmsi}:{event.anomaly_type}",
                    type="ais_anomaly",
                    severity="high" if event.anomaly_type == "sdn_match" else "medium",
                    lat=event.position.get("lat"),
                    lon=event.position.get("lon"),
                    title=f"AIS anomaly: {label}"
                    + (f" — {event.vessel_name}" if event.vessel_name else ""),
                    text=f"MMSI {event.mmsi}: {label} (confidence {event.confidence:.0%}).",
                    url=f"https://www.marinetraffic.com/en/ais/details/ships/mmsi:{event.mmsi}",
                    source="ais",
                    linked_mmsi=event.mmsi,
                    timestamp_utc=event.timestamp_utc,
                    metadata={
                        "source_policy": "official_api",
                        "transport": "ais_stream",
                        "verification_status": "ais_transponder",
                        "is_distress": False,
                        "publication_status": "internal",
                        "report_kind": "ais_anomaly",
                        "coordinate_source": "ais_position",
                        "anomaly_type": event.anomaly_type,
                        "anomaly_confidence": event.confidence,
                        "anomaly_evidence": event.evidence,
                    },
                ),
                dedup_key=f"aisanom:{event.mmsi}:{event.anomaly_type}",
            )
        except Exception:
            logger.debug("AIS anomaly -> intel event failed", exc_info=True)

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
