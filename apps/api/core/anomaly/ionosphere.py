# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ionosphere anomaly detector — Kp (NOAA) + TEC (Madrigal)."""
from __future__ import annotations
import json
import logging
import os
import threading
import time
import urllib.request
import uuid
from typing import Callable, Optional

from pydantic import BaseModel

from core.config import config as _cfg

logger = logging.getLogger(__name__)


class IonosphereAnomalyEvent(BaseModel):
    event_id: str
    timestamp_utc: str
    anomaly_type: str  # kp_storm | tec_perturbation | ballistic_candidate
    regional_kp: float
    vtec_delta: float = 0.0
    baseline_tecu: float = 0.0
    affected_cells: dict = {}
    confidence: float
    source: str = "ionosphere"


class IonosphereAnomalyDetector:
    def __init__(self, mock: bool = False, on_anomaly: Optional[Callable] = None):
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true" or _cfg.MOCK
        self._on_anomaly = on_anomaly
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._kp = 0.0
        self._tec_history: list[float] = []  # rolling 72h baseline

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        kp_interval = 3 * 3600
        tec_interval = 5 * 60
        last_kp = 0.0
        last_tec = 0.0
        while self._running:
            now = time.time()
            if now - last_kp >= kp_interval:
                self._fetch_kp()
                last_kp = now
            if now - last_tec >= tec_interval:
                self._fetch_tec()
                last_tec = now
            time.sleep(30)

    def _fetch_kp(self) -> None:
        if self.mock:
            import random
            self._kp = random.uniform(0.5, 3.5)
            return
        try:
            url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            self._kp = float(data[-1][1])
            if self._kp > 4:
                self._emit_kp_storm()
        except Exception as exc:
            logger.warning("Kp fetch failed: %s", exc)

    def _fetch_tec(self) -> None:
        if self.mock:
            import random, statistics
            vtec = 15.0 + random.gauss(0, 2)
            self._tec_history.append(vtec)
            if len(self._tec_history) > 864:  # 72h at 5min intervals
                self._tec_history.pop(0)
            if len(self._tec_history) > 10:
                baseline = statistics.mean(self._tec_history[:-1])
                sigma = statistics.stdev(self._tec_history[:-1]) + 0.1
                delta = (vtec - baseline) / sigma
                if abs(delta) > 2.5:
                    self._emit_tec_perturbation(vtec, baseline, delta)
            return
        # Real: query Madrigal TEC endpoint (requires free registration)
        try:
            url = (
                f"{_cfg.MADRIGAL_URL}/geospace/earth/madrigal/ub/"
                f"?lat={_cfg.TID_REGION_LAT}&lon={_cfg.TID_REGION_LON}&kinst=31"
            )
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            vtec = float(data.get("vtec", 15.0))
            self._tec_history.append(vtec)
            if len(self._tec_history) > 864:
                self._tec_history.pop(0)
            if len(self._tec_history) > 10:
                import statistics
                baseline = statistics.mean(self._tec_history[:-1])
                sigma = statistics.stdev(self._tec_history[:-1]) + 0.1
                delta = (vtec - baseline) / sigma
                if abs(delta) > 2.5:
                    self._emit_tec_perturbation(vtec, baseline, delta)
        except Exception:
            pass

    def _emit_kp_storm(self) -> None:
        from datetime import datetime, timezone
        self._emit(IonosphereAnomalyEvent(
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            anomaly_type="kp_storm",
            regional_kp=self._kp,
            confidence=min(0.95, (self._kp - 4) / 5 + 0.6),
        ))

    def _emit_tec_perturbation(self, vtec, baseline, sigma_delta) -> None:
        from datetime import datetime, timezone
        delta = vtec - baseline
        cls = "tec_perturbation"
        conf = min(0.90, 0.5 + abs(sigma_delta) / 10)
        if abs(sigma_delta) > 4 and self._kp < 3:
            cls = "ballistic_candidate"
            conf = min(0.88, conf + 0.1)
        self._emit(IonosphereAnomalyEvent(
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            anomaly_type=cls,
            regional_kp=self._kp,
            vtec_delta=round(delta, 2),
            baseline_tecu=round(baseline, 2),
            confidence=conf,
            affected_cells={"lat": _cfg.TID_REGION_LAT, "lon": _cfg.TID_REGION_LON,
                            "sigma": round(sigma_delta, 2)},
        ))

    def _emit(self, event: IonosphereAnomalyEvent) -> None:
        logger.warning("Ionosphere anomaly: %s  conf=%.2f", event.anomaly_type, event.confidence)
        if self._on_anomaly:
            self._on_anomaly(event)
        try:
            import redis  # type: ignore[import]
            r = redis.from_url(os.environ.get("REDIS_URL", _cfg.REDIS_URL))
            r.publish("ionosphere:anomalies", event.model_dump_json())
        except Exception:
            pass


if __name__ == "__main__":
    events: list[IonosphereAnomalyEvent] = []
    det = IonosphereAnomalyDetector(mock=True, on_anomaly=events.append)
    # Inject storm
    det._kp = 5.5
    det._emit_kp_storm()
    # Inject TEC spike
    det._tec_history = [15.0] * 100
    det._emit_tec_perturbation(22.0, 15.0, 3.5)
    print(f"IonosphereAnomalyDetector self-test OK: {len(events)} events")
    for e in events:
        print(f"  {e.anomaly_type}  kp={e.regional_kp}  conf={e.confidence:.2f}")
