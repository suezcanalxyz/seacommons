# SPDX-License-Identifier: AGPL-3.0-or-later
"""Infrasound detector — Raspberry Boom HAT / MCP3208 ADC or MOCK synthetic."""
from __future__ import annotations
import json
import logging
import os
import random
import threading
import time
import uuid
from typing import Any, Callable, Optional

from pydantic import BaseModel

from core.config import config as _cfg

logger = logging.getLogger(__name__)


class InfrasoundEvent(BaseModel):
    event_id: str
    timestamp_utc: str
    classification: str  # impulsive_explosion | sustained_venting | wind_noise | unknown
    confidence: float
    duration_s: float
    peak_pa: float        # peak pressure amplitude (Pascal)
    source: str = "infrasound"


class InfrasoundDetector:
    def __init__(self, mock: bool = False, on_event: Optional[Callable] = None):
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true" or _cfg.MOCK
        self.sta_window = _cfg.INFRASOUND_STA_WINDOW
        self.lta_window = _cfg.INFRASOUND_LTA_WINDOW
        self.trigger_ratio = _cfg.INFRASOUND_TRIGGER_RATIO
        self.sampling_rate = 100.0
        self._on_event = on_event
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._buffer: list[float] = []
        self._lock = threading.Lock()
        self._last_event_time: float = 0.0
        self._cooldown_s: float = 30.0  # min seconds between events

    def start(self) -> None:
        if self._running:
            return
        if not _cfg.INFRASOUND_ENABLED and not self.mock:
            logger.info("INFRASOUND_ENABLED=false and not mock — detector idle")
            return
        self._running = True
        self._thread = threading.Thread(target=self._sta_lta_loop, daemon=True)
        self._thread.start()
        logger.info("InfrasoundDetector started (mock=%s)", self.mock)

    def stop(self) -> None:
        self._running = False

    def _sta_lta_loop(self) -> None:
        buf_size = int(self.lta_window * self.sampling_rate)
        while self._running:
            sample = self._read_hardware()
            with self._lock:
                self._buffer.append(sample)
                if len(self._buffer) > buf_size:
                    self._buffer.pop(0)
                buf = list(self._buffer)
            if len(buf) >= buf_size:
                self._check_trigger(buf)
            time.sleep(1.0 / self.sampling_rate)

    def _read_hardware(self) -> float:
        if self.mock:
            noise = random.gauss(0, 0.02)
            # Rare synthetic impulse (~1/5000 samples)
            if random.random() < 0.0002:
                return noise + random.uniform(0.5, 2.0)
            return noise
        try:
            import spidev  # type: ignore[import]
            spi = spidev.SpiDev()
            spi.open(0, 0)
            spi.max_speed_hz = 1_200_000
            raw = spi.xfer2([0x06 | 0, 0, 0])
            spi.close()
            value = ((raw[1] & 0x0F) << 8) | raw[2]
            return (value - 2048) / 2048.0 * 10.0  # ±10 Pa range
        except Exception:
            return random.gauss(0, 0.01)

    def _check_trigger(self, buf: list[float]) -> None:
        try:
            import numpy as np  # type: ignore[import]
            arr = np.array(buf)
            sta_n = int(self.sta_window * self.sampling_rate)
            lta_n = int(self.lta_window * self.sampling_rate)
            sta = np.mean(arr[-sta_n:] ** 2)
            lta = np.mean(arr[:lta_n] ** 2) + 1e-10
            if sta / lta >= self.trigger_ratio:
                if time.monotonic() - self._last_event_time >= self._cooldown_s:
                    self._emit(buf)
        except ImportError:
            # numpy not available — simple threshold check
            recent = buf[-int(self.sta_window * self.sampling_rate):]
            if max(abs(x) for x in recent) > 0.3:
                if time.monotonic() - self._last_event_time >= self._cooldown_s:
                    self._emit(buf)

    def _emit(self, buf: list[float]) -> None:
        from datetime import datetime, timezone
        duration_s = len(buf) / self.sampling_rate
        cls, conf = self._classify(duration_s, buf)
        event = InfrasoundEvent(
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            classification=cls,
            confidence=conf,
            duration_s=round(duration_s, 1),
            peak_pa=round(max(abs(x) for x in buf), 4),
        )
        self._last_event_time = time.monotonic()
        logger.warning("Infrasound event: %s  conf=%.2f", cls, conf)
        if self._on_event:
            self._on_event(event)
        self._publish(event)

    def _classify(self, duration_s: float, buf: list[float]) -> tuple[str, float]:
        peak = max(abs(x) for x in buf) if buf else 0.0
        if duration_s < 60 and peak > 0.5:
            return "impulsive_explosion", 0.85
        if duration_s > 300:
            return "sustained_venting", 0.75
        if peak < 0.1:
            return "wind_noise", 0.60
        return "unknown", 0.40

    def _publish(self, event: InfrasoundEvent) -> None:
        try:
            import redis  # type: ignore[import]
            r = redis.from_url(os.environ.get("REDIS_URL", _cfg.REDIS_URL))
            r.publish("infrasound:events", event.model_dump_json())
        except Exception:
            pass


if __name__ == "__main__":
    events: list[InfrasoundEvent] = []
    det = InfrasoundDetector(mock=True, on_event=events.append)
    det.start()
    # Inject synthetic burst
    import random as _r
    for _ in range(200):
        det._buffer.append(_r.uniform(0.8, 1.5))
    time.sleep(0.5)
    det._check_trigger(det._buffer)
    det.stop()
    print(f"InfrasoundDetector self-test: {len(events)} events emitted")
    if events:
        print(f"  classification={events[0].classification}  confidence={events[0].confidence}")
