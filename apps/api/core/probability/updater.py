# SPDX-License-Identifier: AGPL-3.0-or-later
"""Environment updater — polls real weather/ocean sources and pushes updates to the ProbabilityEngine."""
from __future__ import annotations

import logging
import math
import os
import threading
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from core.config import config as _cfg
from core.ocean.cmems import fetch_ocean_point

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = float(os.getenv("ENV_POLL_INTERVAL_S", "300"))  # 5 min default


def _coalesce_float(value, default: float) -> float:
    try:
        if value is None:
            return float(default)
        parsed = float(value)
        if not math.isfinite(parsed):
            return float(default)
        return parsed
    except (TypeError, ValueError):
        return float(default)


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
        logger.info("EnvironmentUpdater started (interval=%.0fs)", _POLL_INTERVAL_S)

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
        return self._real_env()

    @staticmethod
    def _real_env() -> dict[str, float]:
        lat = float(os.getenv("ENV_REGION_LAT", str(_cfg.TID_REGION_LAT)))
        lon = float(os.getenv("ENV_REGION_LON", str(_cfg.TID_REGION_LON)))
        url = (
            f"{_cfg.OPEN_METEO_BASE}/forecast"
            f"?latitude={lat:.3f}&longitude={lon:.3f}"
            f"&current=temperature_2m,wind_speed_10m"
            f"&hourly=wave_height"
            f"&wind_speed_unit=ms&forecast_days=1&timezone=UTC"
        )
        with urllib.request.urlopen(url, timeout=_cfg.EXTERNAL_DATA_TIMEOUT_S) as resp:
            import json as _json
            payload = _json.loads(resp.read())
        cur = payload.get("current", {})
        hourly = payload.get("hourly", {})
        wave = _coalesce_float(hourly.get("wave_height", [0.0])[0] if hourly.get("wave_height") else 0.0, 0.0)
        ocean = fetch_ocean_point(lat, lon)
        if not ocean:
            raise RuntimeError("Real CMEMS ocean data unavailable")
        return {
            "water_temp_c": round(_coalesce_float(ocean.get("water_temp_c"), 0.0), 2),
            "air_temp_c": round(_coalesce_float(cur.get("temperature_2m"), 0.0), 2),
            "wind_speed_ms": round(_coalesce_float(cur.get("wind_speed_10m"), 0.0), 2),
            "wave_height_m": round(_coalesce_float(ocean.get("wave_height_m"), wave), 2),
        }
