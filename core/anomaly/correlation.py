# SPDX-License-Identifier: AGPL-3.0-or-later
"""Correlation engine — fuses all sensor channels into classified threat events."""
from __future__ import annotations
import json
import logging
import os
import queue
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from core.config import config as _cfg

logger = logging.getLogger(__name__)

WEIGHTS: dict[str, float] = {
    "infrasound":   0.28,
    "seismic":      0.22,
    "hydrophone":   0.12,
    "adsb":         0.10,
    "ais_anomaly":  0.08,
    "ionospheric":  0.08,
    "gnss_spoof":   0.07,
    "traffic":      0.05,
}

_CHANNEL_MAP: dict[str, str] = {
    "infrasound:events":    "infrasound",
    "seismic:events":       "seismic",
    "hydro:events":         "hydrophone",
    "adsb:anomalies":       "adsb",
    "ais:anomalies":        "ais_anomaly",
    "sensors:ionospheric":  "ionospheric",
    "ionosphere:anomalies": "ionospheric",
    "gnss:anomalies":       "gnss_spoof",
    "traffic:anomalies":    "traffic",
    "weather:alerts":       "weather",
    "sdr:anomalies":        "adsb",
}

_WINDOW_S = 120  # doubled vs v1 to capture slow TID propagation


class CorrelationEngine:
    def __init__(self, on_threat: Optional[Callable] = None, in_memory: bool = False):
        """
        Args:
            on_threat: callback(event_dict) for emitted threats.
            in_memory: if True, use internal queue instead of Redis pubsub.
        """
        self._on_threat = on_threat
        self._in_memory = in_memory
        self._queue: queue.Queue = queue.Queue()
        self._recent: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self.alert_threshold = _cfg.CORRELATION_CONFIDENCE_ALERT
        self.urgent_threshold = _cfg.CORRELATION_CONFIDENCE_URGENT
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._r = None

    def start(self) -> None:
        self._running = True
        if self._in_memory:
            self._thread = threading.Thread(target=self._queue_loop, daemon=True)
        else:
            self._thread = threading.Thread(target=self._redis_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def ingest(self, channel: str, data: dict) -> None:
        """Directly inject an event (in-memory mode, or for testing)."""
        self._queue.put((channel, data))

    # ── In-memory loop ──────────────────────────────────────────────────────
    def _queue_loop(self) -> None:
        while self._running:
            try:
                channel, data = self._queue.get(timeout=1)
                self._process(channel, data)
            except queue.Empty:
                pass

    # ── Redis pubsub loop ───────────────────────────────────────────────────
    def _redis_loop(self) -> None:
        try:
            import redis  # type: ignore[import]
            r = redis.from_url(os.environ.get("REDIS_URL", _cfg.REDIS_URL))
            self._r = r
            ps = r.pubsub()
            ps.subscribe(*list(_CHANNEL_MAP.keys()))
            for msg in ps.listen():
                if not self._running:
                    break
                if msg["type"] == "message":
                    ch = msg["channel"].decode()
                    try:
                        data = json.loads(msg["data"].decode())
                    except Exception:
                        continue
                    # Suppress ionospheric if geomagnetic storm is active
                    if _CHANNEL_MAP.get(ch) == "ionospheric":
                        if r.get("GEOMAGNETIC_STORM_ACTIVE") == b"true":
                            continue
                        if data.get("confidence", 0) < 0.50:
                            continue
                    self._process(ch, data)
        except Exception as exc:
            logger.error("CorrelationEngine Redis loop error: %s", exc)

    def _process(self, channel: str, data: dict) -> None:
        sensor_type = _CHANNEL_MAP.get(channel, "unknown")
        now = datetime.now(timezone.utc).timestamp()
        with self._lock:
            self._recent.append({"type": sensor_type, "timestamp": now, "data": data})
            self._recent = [e for e in self._recent if now - e["timestamp"] < _WINDOW_S]
            self._evaluate()

    def _evaluate(self) -> float:
        seen = {e["type"] for e in self._recent}
        confidence = sum(WEIGHTS.get(t, 0.0) for t in seen)
        if confidence >= self.alert_threshold:
            self._emit_threat(confidence, seen)
            self._recent.clear()
        return confidence

    def _emit_threat(self, confidence: float, sources: set[str]) -> None:
        # Classification logic
        if ("ionospheric" in sources
                and ("infrasound" in sources or "seismic" in sources)
                and confidence >= self.urgent_threshold):
            classification = "ballistic_confirmed"
        elif "adsb" in sources and "infrasound" in sources and confidence >= self.alert_threshold:
            classification = "drone_attack_candidate"
        elif "ais_anomaly" in sources and "gnss_spoof" in sources and confidence >= self.alert_threshold:
            classification = "vessel_spoofing_confirmed"
        else:
            classification = "physical_threat_candidate"

        # Gather sensor data from contributing events
        sensor_data: dict[str, Any] = {}
        for src in sources:
            items = [e["data"] for e in self._recent if e["type"] == src]
            if items:
                sensor_data[src] = items[0]

        threat: dict[str, Any] = {
            "type": "PhysicalThreatEvent",
            "classification": classification,
            "confidence": round(confidence, 4),
            "sources": sorted(sources),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "urgent": confidence >= self.urgent_threshold,
            "sensor_data": sensor_data,
        }

        logger.warning("THREAT EMITTED: %s  confidence=%.2f  sources=%s",
                       classification, confidence, sorted(sources))

        if self._on_threat:
            self._on_threat(threat)

        # Publish to Redis
        if self._r:
            self._r.publish("physical_threat:events", json.dumps(threat))

        # Sign and store forensic packet
        self._forensic_log(threat, sensor_data)

    def _forensic_log(self, threat: dict, sensor_data: dict) -> None:
        try:
            from core.forensic.packet import ForensicPacket
            from core.forensic.logger import sign_and_store
            from datetime import timezone
            pkt = ForensicPacket(
                timestamp_utc=threat["timestamp_utc"],
                classification=threat["classification"],
                confidence=threat["confidence"],
                position=sensor_data.get("ais_anomaly", {}).get("position",
                         {"lat": 0, "lon": 0, "alt": 0, "source": "unknown"}),
                contributing_sensors=threat["sources"],
                sensor_data=sensor_data,
            )
            sign_and_store(pkt)
        except Exception as exc:
            logger.warning("Forensic log failed: %s", exc)


def test_correlation_engine():
    """Unit test — runs without Redis."""
    threats = []
    engine = CorrelationEngine(on_threat=threats.append, in_memory=True)
    now = datetime.now(timezone.utc).timestamp()

    # Test 1: infrasound alone (0.28) — below threshold 0.55
    engine._recent = [{"type": "infrasound", "timestamp": now, "data": {}}]
    c1 = engine._evaluate()
    assert abs(c1 - 0.28) < 0.001, f"Expected 0.28 got {c1}"
    assert len(engine._recent) == 1

    # Test 2: infrasound + seismic = 0.50 — still below 0.55
    engine._recent = [
        {"type": "infrasound", "timestamp": now, "data": {}},
        {"type": "seismic",    "timestamp": now, "data": {}},
    ]
    c2 = engine._evaluate()
    assert abs(c2 - 0.50) < 0.001, f"Expected 0.50 got {c2}"
    assert len(engine._recent) == 2

    # Test 3: infrasound + seismic + hydrophone = 0.62 — exceeds 0.55
    engine._recent = [
        {"type": "infrasound",  "timestamp": now, "data": {}},
        {"type": "seismic",     "timestamp": now, "data": {}},
        {"type": "hydrophone",  "timestamp": now, "data": {}},
    ]
    c3 = engine._evaluate()
    assert abs(c3 - 0.62) < 0.001, f"Expected 0.62 got {c3}"
    assert len(threats) == 1
    assert len(engine._recent) == 0  # cleared after emit

    # Test 4: ballistic_confirmed requires ionospheric + infrasound/seismic + 0.80
    engine._recent = [
        {"type": "infrasound",  "timestamp": now, "data": {}},
        {"type": "seismic",     "timestamp": now, "data": {}},
        {"type": "ionospheric", "timestamp": now, "data": {}},
        {"type": "hydrophone",  "timestamp": now, "data": {}},
        {"type": "adsb",        "timestamp": now, "data": {}},
    ]
    c4 = engine._evaluate()
    assert len(threats) == 2
    assert threats[-1]["classification"] == "ballistic_confirmed", threats[-1]["classification"]

    print("CorrelationEngine unit tests passed.")
    for t in threats:
        print(f"  {t['classification']}  confidence={t['confidence']}")


if __name__ == "__main__":
    test_correlation_engine()
