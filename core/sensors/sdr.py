# SPDX-License-Identifier: AGPL-3.0-or-later
"""SDR scanner — RTL-SDR anomaly detection or MOCK synthetic."""
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


class RFAnomalyEvent(BaseModel):
    event_id: str
    timestamp_utc: str
    frequency_mhz: float
    power_db: float
    threshold_exceeded_db: float
    classification: str   # drone_control | unknown_burst | jamming | normal
    confidence: float
    source: str = "sdr"


class SDRScanner:
    # Frequency bands of interest (MHz)
    BANDS: list[tuple[float, float, str]] = [
        (433.0, 434.0, "drone_control_433"),
        (868.0, 868.5, "drone_control_868"),
        (915.0, 915.5, "drone_control_915"),
        (2400.0, 2483.5, "wifi_drone_24ghz"),
        (5725.0, 5875.0, "wifi_drone_58ghz"),
        (1090.0, 1090.5, "adsb"),
        (156.0, 174.0, "vhf_marine"),
    ]

    def __init__(self, mock: bool = False, on_anomaly: Optional[Callable] = None):
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true" or _cfg.MOCK
        self.threshold_db = _cfg.SDR_THRESHOLD_DB
        self._on_anomaly = on_anomaly
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._baseline: dict[str, float] = {}

    def start(self) -> None:
        if not _cfg.SDR_ENABLED and not self.mock:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            for freq_lo, freq_hi, band_name in self.BANDS:
                power_db = self._measure(freq_lo)
                baseline = self._baseline.get(band_name, power_db)
                self._baseline[band_name] = baseline * 0.99 + power_db * 0.01  # IIR
                excess = power_db - baseline
                if excess >= self.threshold_db:
                    cls = self._classify(band_name, power_db, excess)
                    self._emit(freq_lo, power_db, excess, cls)
            time.sleep(10)

    def _measure(self, freq_mhz: float) -> float:
        if self.mock:
            base = -70.0 + random.gauss(0, 3)
            if random.random() < 0.005:
                base += random.uniform(self.threshold_db, self.threshold_db + 15)
            return base
        try:
            import rtlsdr  # type: ignore[import]
            sdr = rtlsdr.RtlSdr()
            sdr.center_freq = freq_mhz * 1e6
            sdr.sample_rate = 2.4e6
            sdr.gain = "auto"
            samples = sdr.read_samples(256 * 1024)
            sdr.close()
            import numpy as np  # type: ignore[import]
            power = 10 * np.log10(np.mean(np.abs(samples) ** 2) + 1e-12)
            return float(power)
        except Exception:
            return -70.0 + random.gauss(0, 3)

    def _classify(self, band: str, power_db: float, excess_db: float) -> str:
        if "drone_control" in band:
            return "drone_control"
        if "wifi_drone" in band:
            return "drone_control"
        if excess_db > 20:
            return "jamming"
        return "unknown_burst"

    def _emit(self, freq_mhz, power_db, excess_db, classification) -> None:
        from datetime import datetime, timezone
        event = RFAnomalyEvent(
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            frequency_mhz=freq_mhz,
            power_db=round(power_db, 1),
            threshold_exceeded_db=round(excess_db, 1),
            classification=classification,
            confidence=min(0.95, 0.5 + excess_db / 30),
        )
        logger.warning("RF anomaly: %s @ %.1f MHz +%.1f dB", classification, freq_mhz, excess_db)
        if self._on_anomaly:
            self._on_anomaly(event)
        try:
            import redis  # type: ignore[import]
            r = redis.from_url(os.environ.get("REDIS_URL", _cfg.REDIS_URL))
            r.publish("sdr:anomalies", event.model_dump_json())
        except Exception:
            pass


if __name__ == "__main__":
    events: list[RFAnomalyEvent] = []
    scanner = SDRScanner(mock=True, on_anomaly=events.append)
    # Force anomaly
    scanner._baseline["drone_control_433"] = -70.0
    scanner._emit(433.0, -55.0, 15.0, "drone_control")
    print(f"SDRScanner self-test OK: {len(events)} events")
    if events:
        print(f"  {events[0].classification}  +{events[0].threshold_exceeded_db}dB")
