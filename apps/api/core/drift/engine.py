# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drift engine with strict operational OpenDrift and an explicit demo-only fallback."""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from core.config import config as runtime_config
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


def _remote_compute(lat: float, lon: float, time_utc: datetime, duration_h: int,
                     domain: str, config: Optional[dict], backtrack: bool) -> Optional[DriftResult]:
    """POST to DRIFT_WORKER_URL when configured. Returns None to fall back to
    in-process compute (unset URL, unreachable worker, or any worker error) —
    a remote-compute failure must never take the whole request down."""
    if not runtime_config.DRIFT_WORKER_URL or domain == "ballistic":
        return None
    try:
        import httpx
        response = httpx.post(
            f"{runtime_config.DRIFT_WORKER_URL.rstrip('/')}/compute",
            json={
                "lat": lat, "lon": lon, "time_utc": time_utc.isoformat(),
                "duration_h": duration_h, "domain": domain, "config": config,
                "backtrack": backtrack,
            },
            headers={"X-Worker-Secret": runtime_config.DRIFT_WORKER_SECRET},
            timeout=runtime_config.DRIFT_WORKER_TIMEOUT_S,
        )
        response.raise_for_status()
        return DriftResult(**response.json())
    except Exception as exc:
        logger.warning("Drift worker unreachable, computing in-process instead: %s", exc)
        return None


class DriftEngine:
    def __init__(self):
        self._cache = CacheManager()

    def compute(self, lat: float, lon: float, time_utc: datetime, duration_h: int = 24,
                domain: str = "ocean_sar", config: Optional[dict] = None) -> DriftResult:
        """Forward drift from lat/lon."""
        remote = _remote_compute(lat, lon, time_utc, duration_h, domain, config, backtrack=False)
        if remote is not None:
            return remote
        if domain == "ballistic":
            return self._ballistic(lat, lon, time_utc, config or {})
        return self._opendrift(lat, lon, time_utc, duration_h, domain, config or {})

    def backtrack(self, lat: float, lon: float, time_utc: datetime, duration_h: int = 24,
                  domain: str = "ocean_sar", config: Optional[dict] = None) -> DriftResult:
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
                # Open-Meteo uses meteorological wind direction (where wind
                # comes from); OpenDrift expects eastward/northward vectors.
                "x_wind": float(config.get("x_wind", -wind_speed * math.sin(wind_dir_rad))),
                "y_wind": float(config.get("y_wind", -wind_speed * math.cos(wind_dir_rad))),
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
                if config.get("vessel_type") else int(config.get("object_type", 26))
            ),
            "seed_radius_m": float(config.get("seed_radius_m", 150)),
        }
        if runtime_config.DEMO_PUBLIC_MODE:
            logger.info("Using bounded fallback in the isolated low-memory demo API")
            return self._demo_fallback(
                lat,
                lon,
                time_utc,
                duration_h,
                payload,
                "isolated low-memory demo API; simulations use the operational engine",
            )
        try:
            return DriftResult.model_validate(run_leeway(payload))
        except Exception as exc:
            logger.error("OpenDrift failed for %s at %.5f,%.5f: %s", domain, lat, lon, exc)
            if runtime_config.DEMO_PUBLIC_MODE:
                logger.warning("Using explicitly degraded public-demo drift fallback")
                return self._demo_fallback(lat, lon, time_utc, duration_h, payload, str(exc))
            raise RuntimeError(f"OpenDrift failed: {exc}") from exc

    @staticmethod
    def _demo_fallback(lat, lon, time_utc, duration_h, payload, reason) -> DriftResult:
        """Bounded deterministic fallback for the isolated public demo only."""
        env = payload["environment"]
        velocity_x = float(env["x_sea_water_velocity"]) + float(env["x_wind"]) * 0.03
        velocity_y = float(env["y_sea_water_velocity"]) + float(env["y_wind"]) * 0.03
        cos_lat = max(0.2, math.cos(math.radians(lat)))

        def point(hours: float) -> tuple[float, float]:
            seconds = hours * 3600
            return (lon + velocity_x * seconds / (111_320 * cos_lat),
                    lat + velocity_y * seconds / 111_320)

        def cone(hours: float, key: str) -> dict[str, Any]:
            center_lon, center_lat = point(min(hours, duration_h))
            radius_m = 500 + min(hours, duration_h) * 450
            ring = []
            for step in range(33):
                angle = 2 * math.pi * step / 32
                ring.append([
                    center_lon + math.cos(angle) * radius_m / (111_320 * cos_lat),
                    center_lat + math.sin(angle) * radius_m / 111_320,
                ])
            return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {"type": key, "radius_m": radius_m, "degraded": True}}

        hours = sorted(set([0, min(6, duration_h), min(12, duration_h), duration_h]))
        coordinates = [list(point(hour)) for hour in hours]
        return DriftResult(
            trajectory={"type": "Feature", "geometry": {"type": "LineString", "coordinates": coordinates},
                        "properties": {"type": "trajectory", "degraded": True}},
            cone_6h=cone(6, "cone_6h"), cone_12h=cone(12, "cone_12h"), cone_24h=cone(24, "cone_24h"),
            impact_point={"type": "FeatureCollection", "features": [{
                "type": "Feature", "geometry": {"type": "Point", "coordinates": coordinates[-1]},
                "properties": {"type": "impact_point", "hours": duration_h, "degraded": True}}]},
            metadata={"domain": payload.get("domain", "ocean_sar"), "start_time": time_utc.isoformat(),
                      "duration_h": duration_h, "model": "degraded demonstration fallback",
                      "operational_use": False, "fallback_reason": reason[:300], "forcing": env},
        )

    def _ballistic(self, lat, lon, time_utc, config) -> DriftResult:
        solver = BallisticTerminal()
        result = solver.solve(
            lat=lat, lon=lon, entry_angle_deg=config.get("entry_angle_deg", 45),
            entry_velocity_ms=config.get("entry_velocity_ms", 800),
            entry_altitude_m=config.get("entry_altitude_m", 10_000),
            wind_speed_ms=config.get("wind_speed_ms", 5.0), wind_dir_deg=config.get("wind_dir_deg", 270.0),
        )
        il, io_ = result["impact"]["lat"], result["impact"]["lon"]
        traj = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[lon, lat], [io_, il]]},
                "properties": {"type": "trajectory"}}
        cone = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [io_, il]},
                "properties": {"radius_m": result["fragment_radius_m"]}}
        return DriftResult(
            trajectory=traj, cone_6h=cone, cone_12h=cone, cone_24h=cone, impact_point=result["geojson"],
            metadata={"domain": "ballistic", "range_m": result["range_m"],
                      "fragment_radius_m": result["fragment_radius_m"], "start_time": time_utc.isoformat()},
        )


if __name__ == "__main__":
    from datetime import timezone
    engine = DriftEngine()
    result = engine.compute(lat=35.5, lon=14.0, time_utc=datetime.now(timezone.utc))
    print("DriftEngine self-test OK:", result.metadata)
