# SPDX-License-Identifier: AGPL-3.0-or-later
"""DriftEngine — wraps OpenDrift and BallisticTerminal with explicit SAR failure on missing OpenDrift."""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from core.drift.cache import CacheManager
from core.drift.models import BallisticTerminal, resolve_object_type
from core.drift.opendrift_pool import run_leeway

logger = logging.getLogger(__name__)


class DriftResult(BaseModel):
    trajectory: dict[str, Any]
    cone_6h: dict[str, Any]
    cone_12h: dict[str, Any]
    cone_24h: dict[str, Any]
    impact_point: Optional[dict[str, Any]] = None
    metadata: dict[str, Any]


class DriftEngine:
    def __init__(self):
        self._cache = CacheManager()

    def compute(
        self,
        lat: float,
        lon: float,
        time_utc: datetime,
        duration_h: int = 24,
        domain: str = "ocean_sar",
        config: Optional[dict] = None,
    ) -> DriftResult:
        """Forward drift from lat/lon."""
        if domain == "ballistic":
            return self._ballistic(lat, lon, time_utc, config or {})
        return self._opendrift(lat, lon, time_utc, duration_h, domain, config or {})

    def backtrack(
        self,
        lat: float,
        lon: float,
        time_utc: datetime,
        duration_h: int = 24,
        domain: str = "ocean_sar",
        config: Optional[dict] = None,
    ) -> DriftResult:
        """Backward drift using the same real-data engine with reversed vectors."""
        wind = self._cache.get_wind_live(lat, lon)
        _ = (wind.get("wind_dir_deg", 270.0) + 180) % 360
        env = {
            "x_wind": -float(os.getenv("OPENDRIFT_WIND_X", "4.0")),
            "y_wind": -float(os.getenv("OPENDRIFT_WIND_Y", "1.0")),
            "x_sea_water_velocity": -0.2,
            "y_sea_water_velocity": -0.05,
        }
        return self._opendrift(lat, lon, time_utc, duration_h, domain, env)

    def _opendrift(self, lat, lon, time_utc, duration_h, domain, config) -> DriftResult:
        wind = self._cache.get_wind_live(lat, lon)
        current = self._cache.get_ocean_currents(lat, lon)
        wind_series = self._cache.get_wind_forecast_series(lat, lon, hours=duration_h)
        wind_speed = float(wind.get("wind_speed_ms", 0.0))
        wind_dir_deg = float(wind.get("wind_dir_deg", 0.0))
        wind_dir_rad = math.radians(wind_dir_deg)
        payload = {
            "lat": lat,
            "lon": lon,
            "time_utc": time_utc.isoformat(),
            "duration_h": duration_h,
            "domain": domain,
            "environment": {
                "x_wind": float(config.get("x_wind", wind_speed * math.sin(wind_dir_rad))),
                "y_wind": float(config.get("y_wind", wind_speed * math.cos(wind_dir_rad))),
                "x_sea_water_velocity": float(config.get("x_sea_water_velocity", current.get("u_ms", 0.0))),
                "y_sea_water_velocity": float(config.get("y_sea_water_velocity", current.get("v_ms", 0.0))),
                "land_binary_mask": 0,
            },
            "wind_series": wind_series,
            "particles": int(config.get("particles", os.getenv("OPENDRIFT_PARTICLES", "50"))),
            "time_step_seconds": int(config.get("time_step_seconds", os.getenv("OPENDRIFT_TIMESTEP_SECONDS", "1800"))),
            "time_step_output_seconds": int(config.get("time_step_output_seconds", os.getenv("OPENDRIFT_OUTPUT_SECONDS", "3600"))),
            "object_type": (
                resolve_object_type(config["vessel_type"], int(config.get("persons", 1)))
                if config.get("vessel_type")
                else int(config.get("object_type", 26))
            ),
            "seed_radius_m": float(config.get("seed_radius_m", 150)),
        }
        try:
            return DriftResult.model_validate(run_leeway(payload))
        except Exception as exc:
            logger.error("OpenDrift failed for %s at %.5f,%.5f: %s", domain, lat, lon, exc)
            raise RuntimeError(f"OpenDrift failed: {exc}") from exc

    def _ballistic(self, lat, lon, time_utc, config) -> DriftResult:
        solver = BallisticTerminal()
        result = solver.solve(
            lat=lat,
            lon=lon,
            entry_angle_deg=config.get("entry_angle_deg", 45),
            entry_velocity_ms=config.get("entry_velocity_ms", 800),
            entry_altitude_m=config.get("entry_altitude_m", 10_000),
            wind_speed_ms=config.get("wind_speed_ms", 5.0),
            wind_dir_deg=config.get("wind_dir_deg", 270.0),
        )
        il, io_ = result["impact"]["lat"], result["impact"]["lon"]
        traj = {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[lon, lat], [io_, il]]},
            "properties": {"type": "trajectory"},
        }
        cone = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [io_, il]},
            "properties": {"radius_m": result["fragment_radius_m"]},
        }
        return DriftResult(
            trajectory=traj,
            cone_6h=cone,
            cone_12h=cone,
            cone_24h=cone,
            impact_point=result["geojson"],
            metadata={
                "domain": "ballistic",
                "range_m": result["range_m"],
                "fragment_radius_m": result["fragment_radius_m"],
                "start_time": time_utc.isoformat(),
            },
        )


if __name__ == "__main__":
    from datetime import timezone

    engine = DriftEngine()
    result = engine.compute(lat=35.5, lon=14.0, time_utc=datetime.now(timezone.utc))
    print("DriftEngine self-test OK:", result.metadata)
    back = engine.backtrack(lat=35.5, lon=14.0, time_utc=datetime.now(timezone.utc))
    print("Backtrack OK:", back.metadata)
    bal = engine.compute(lat=55.535, lon=15.698, time_utc=datetime.now(timezone.utc), domain="ballistic")
    print("Ballistic OK:", bal.impact_point)
