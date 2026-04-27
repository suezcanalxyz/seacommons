# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seismic detector — ADXL355 via SPI or MOCK synthetic."""
from __future__ import annotations
import logging
import os
import random
import threading
import time
import uuid
from typing import Callable, Optional

from pydantic import BaseModel

from core.config import config as _cfg

logger = logging.getLogger(__name__)


class SeismicEvent(BaseModel):
    event_id: str
    timestamp_utc: str
    classification: str   # tectonic | explosion_candidate | noise
    confidence: float
    ps_ratio: float
    peak_acceleration_g: float
    source: str = "seismic"


class SeismicDetector:
    def __init__(self, mock: bool = False, on_event: Optional[Callable] = None):
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true" or _cfg.MOCK
        self._on_event = on_event
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._buffer: list[float] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        if not _cfg.SEISMIC_ENABLED and not self.mock:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        window = 1000  # 10 s at 100 Hz
        while self._running:
            sample = self._read_hardware()
            with self._lock:
                self._buffer.append(sample)
                if len(self._buffer) > window:
                    self._buffer.pop(0)
                buf = list(self._buffer)
            if len(buf) >= window and len(buf) % 100 == 0:
                self._analyze(buf)
            time.sleep(0.01)

    def _read_hardware(self) -> float:
        if self.mock:
            val = random.gauss(0, 0.001)
            if random.random() < 0.001:
                val += random.gauss(0, 0.15)
            return val
        try:
            import spidev  # type: ignore[import]
            spi = spidev.SpiDev()
            spi.open(0, 0)
            spi.max_speed_hz = 1_000_000
            data = spi.xfer2([0x08 << 1 | 0x01, 0, 0])
            spi.close()
            raw = (data[1] << 12) | (data[2] << 4)
            return raw / (1 << 20) * 8.0
        except Exception:
            return random.gauss(0, 0.001)

    def _analyze(self, buf: list[float]) -> None:
        from datetime import datetime, timezone
        half = len(buf) // 2
        p_energy = sum(x**2 for x in buf[:half])
        s_energy = sum(x**2 for x in buf[half:]) + 1e-10
        ps_ratio = p_energy / s_energy
        peak_g = max(abs(x) for x in buf)
        if peak_g < 0.005:
            return
        if ps_ratio > 10:
            cls, conf = "tectonic", min(0.90, 0.5 + ps_ratio * 0.02)
        elif 3 <= ps_ratio <= 8:
            cls, conf = "explosion_candidate", min(0.85, 0.4 + ps_ratio * 0.05)
        else:
            cls, conf = "noise", 0.10
        event = SeismicEvent(
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            classification=cls,
            confidence=conf,
            ps_ratio=round(ps_ratio, 2),
            peak_acceleration_g=round(peak_g, 4),
        )
        if self._on_event:
            self._on_event(event)
        self._publish(event)

    def _publish(self, event: SeismicEvent) -> None:
        try:
            import redis  # type: ignore[import]
            r = redis.from_url(os.environ.get("REDIS_URL", _cfg.REDIS_URL))
            r.publish("seismic:events", event.model_dump_json())
        except Exception:
            pass


if __name__ == "__main__":
    events: list[SeismicEvent] = []
    det = SeismicDetector(mock=True, on_event=events.append)
    det.start()
    # Inject P-wave burst
    for _ in range(200):
        det._buffer.append(random.uniform(0.08, 0.20))
    time.sleep(0.3)
    det._analyze(det._buffer + [random.gauss(0, 0.001)] * 800)
    det.stop()
    print(f"SeismicDetector self-test: {len(events)} events")
    if events:
        print(f"  {events[0].classification}  ps={events[0].ps_ratio}")
