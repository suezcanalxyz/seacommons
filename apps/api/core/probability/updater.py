# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Environment updater — polls weather/ocean sensors and pushes updates
to the ProbabilityEngine.

In MOCK=true mode, returns synthetic values that change slowly over time.
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_MOCK = os.getenv("MOCK", "false").lower() in ("1", "true", "yes")
_POLL_INTERVAL_S = float(os.getenv("ENV_POLL_INTERVAL_S", "300"))  # 5 min default


class EnvironmentUpdater:
    """
    Periodically fetches environmental conditions and calls
    engine.update_environment(**kwargs).

    Usage:
        updater = EnvironmentUpdater(engine)
        updater.start()          # background thread
        ...
        updater.stop()
    """

    def __init__(self, engine: object) -> None:
        self._engine = engine
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run, name="env-updater", daemon=True)
        self._thread.start()
        logger.info("EnvironmentUpdater started (mock=%s, interval=%.0fs)",
                    _MOCK, _POLL_INTERVAL_S)

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=5)

    def fetch_now(self) -> dict[str, float]:
        """Fetch current conditions and update engine immediately."""
        data = self._fetch()
        self._engine.update_environment(**data)   # type: ignore[attr-defined]
        return data

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                data = self._fetch()
                self._engine.update_environment(**data)  # type: ignore[attr-defined]
                logger.debug("env update: %s", data)
            except Exception as exc:
                logger.warning("env fetch error: %s", exc)
            self._stop_evt.wait(_POLL_INTERVAL_S)

    def _fetch(self) -> dict[str, float]:
        mock = os.getenv("MOCK", "false").lower() in ("1", "true", "yes")
        if mock:
            return self._mock_env()
        try:
            return self._real_env()
        except Exception as exc:
            logger.warning("real environment unavailable, using mock fallback: %s", exc)
            return self._mock_env()

    @staticmethod
    def _mock_env() -> dict[str, float]:
        """
        Synthetic Mediterranean conditions that oscillate gently.
        Uses elapsed time so values drift realistically in demos.
        """
        t = time.monotonic()
        water_temp = 18.0 + 2.0 * math.sin(t / 3600)   # 16–20 °C
        air_temp   = 20.0 + 3.0 * math.sin(t / 7200)   # 17–23 °C
        wind_ms    =  5.0 + 3.0 * abs(math.sin(t / 1800))  # 5–8 m/s
        wave_m     =  0.8 + 0.4 * abs(math.sin(t / 2400))  # 0.8–1.2 m
        return {
            "water_temp_c":  round(water_temp, 2),
            "air_temp_c":    round(air_temp, 2),
            "wind_speed_ms": round(wind_ms, 2),
            "wave_height_m": round(wave_m, 2),
        }

    @staticmethod
    def _real_env() -> dict[str, float]:
        """
        Fetch from real APIs (Copernicus Marine, Open-Meteo, etc.)
        Stub — implement when API keys are available.
        """
        # TODO: integrate Copernicus Marine Service + Open-Meteo
        raise NotImplementedError(
            "Real environment fetch not yet implemented. Set MOCK=true.")
