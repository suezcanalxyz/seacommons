# SPDX-License-Identifier: AGPL-3.0-or-later
"""DriftEngine — wraps OpenDrift and BallisticTerminal with explicit SAR failure on missing OpenDrift."""
from __future__ import annotations
import json
import logging
import math
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from core.config import config
from core.drift.models import BallisticTerminal, resolve_object_type
from core.drift.cache import CacheManager

logger = logging.getLogger(__name__)

_OPENDRIFT_RUNNER = Path(__file__).parent.parent.parent / "core" / "drift" / "opendrift_runner.py"


class DriftResult(BaseModel):
    trajectory: dict[str, Any]
    cone_6h: dict[str, Any]
    cone_12h: dict[str, Any]
    cone_24h: dict[str, Any]
    impact_point: Optional[dict[str, Any]] = None
    metadata: dict[str, Any]


class DriftEngine:
    def __init__(self, mock: bool = False):
        self.mock = mock or os.environ.get("MOCK", "false").lower() == "true"
        self.demo_public_mode = config.DEMO_PUBLIC_MODE
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
        if self.mock:
            if domain == "ocean_sar" and not self.demo_public_mode:
                raise RuntimeError("SAR pilot requires real OpenDrift; MOCK mode is not allowed for ocean_sar")
            return self._gaussian_drift(lat, lon, time_utc, duration_h, domain,
                                        vessel_type=(config or {}).get("vessel_type"))
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
        """Backward drift — reverse wind and current vectors."""
        wind = self._mock_wind(lat, lon) if self.mock else self._cache.get_wind_live(lat, lon)
        rev_wind_dir = (wind.get("wind_dir_deg", 270.0) + 180) % 360
        env = {
            "x_wind": -float(os.getenv("OPENDRIFT_WIND_X", "4.0")),
            "y_wind": -float(os.getenv("OPENDRIFT_WIND_Y", "1.0")),
            "x_sea_water_velocity": -0.2,
            "y_sea_water_velocity": -0.05,
        }
        if self.mock:
            raise RuntimeError("SAR backtrack requires real OpenDrift; MOCK mode is not allowed")
        return self._opendrift(lat, lon, time_utc, duration_h, domain, env)

    # ── OpenDrift subprocess ────────────────────────────────────────────────
    def _opendrift(
        self, lat, lon, time_utc, duration_h, domain, config
    ) -> DriftResult:
        python_bin = os.getenv("OPENDRIFT_PYTHON", sys.executable)
        runner = str(_OPENDRIFT_RUNNER)
        if not Path(runner).exists():
            raise RuntimeError("OpenDrift runner not found")
        wind = self._cache.get_wind_live(lat, lon)
        current = self._cache.get_ocean_currents(lat, lon)
        wind_series = self._cache.get_wind_forecast_series(lat, lon, hours=duration_h)
        wind_speed = float(wind.get("wind_speed_ms", 0.0))
        wind_dir_deg = float(wind.get("wind_dir_deg", 0.0))
        wind_dir_rad = math.radians(wind_dir_deg)
        payload = {
            "lat": lat, "lon": lon,
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
            "particles": int(config.get("particles", os.getenv("OPENDRIFT_PARTICLES", "128"))),
            "time_step_seconds": int(config.get("time_step_seconds", os.getenv("OPENDRIFT_TIMESTEP_SECONDS", "900"))),
            "time_step_output_seconds": int(config.get("time_step_output_seconds", os.getenv("OPENDRIFT_OUTPUT_SECONDS", "3600"))),
            "object_type": (
                resolve_object_type(config["vessel_type"], int(config.get("persons", 1)))
                if config.get("vessel_type")
                else int(config.get("object_type", 26))
            ),
            "seed_radius_m": float(config.get("seed_radius_m", 150)),
        }
        try:
            proc = subprocess.run(
                [python_bin, runner],
                input=json.dumps(payload), capture_output=True, text=True, timeout=180,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip())
            return DriftResult.model_validate(json.loads(proc.stdout))
        except Exception as exc:
            logger.error("OpenDrift failed for %s at %.5f,%.5f: %s", domain, lat, lon, exc)
            raise RuntimeError(f"OpenDrift failed: {exc}") from exc

    # ── Ballistic terminal ──────────────────────────────────────────────────
    def _ballistic(self, lat, lon, time_utc, config) -> DriftResult:
        solver = BallisticTerminal()
        result = solver.solve(
            lat=lat, lon=lon,
            entry_angle_deg=config.get("entry_angle_deg", 45),
            entry_velocity_ms=config.get("entry_velocity_ms", 800),
            entry_altitude_m=config.get("entry_altitude_m", 10_000),
            wind_speed_ms=config.get("wind_speed_ms", 5.0),
            wind_dir_deg=config.get("wind_dir_deg", 270.0),
        )
        il, io_ = result["impact"]["lat"], result["impact"]["lon"]
        traj = {"type": "Feature", "geometry": {"type": "LineString",
                "coordinates": [[lon, lat], [io_, il]]}, "properties": {"type": "trajectory"}}
        cone = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [io_, il]},
                "properties": {"radius_m": result["fragment_radius_m"]}}
        return DriftResult(
            trajectory=traj, cone_6h=cone, cone_12h=cone, cone_24h=cone,
            impact_point=result["geojson"],
            metadata={"domain": "ballistic", "range_m": result["range_m"],
                      "fragment_radius_m": result["fragment_radius_m"],
                      "start_time": time_utc.isoformat()},
        )

    # ── Position-specific mock wind ────────────────────────────────────────
    @staticmethod
    def _mock_wind(lat: float, lon: float) -> dict:
        """Generate spatially-varying mock wind keyed to lat/lon — matches weather.py logic."""
        import time as _time
        t = _time.monotonic()
        seed = int(abs(lat) * 100 + abs(lon) * 10) % 997
        speed = 5.0 + 4.0 * abs(math.sin(t / 1800 + seed))      # 5–9 m/s
        direction = (200 + 80 * math.sin(t / 3600 + seed)) % 360 # ~SW quadrant
        return {"wind_speed_ms": round(speed, 2), "wind_dir_deg": round(direction, 1), "source": "mock"}

    # ── Monte-Carlo fallback with Open-Meteo hourly forecast ────────────────
    def _gaussian_drift(
        self,
        lat: float,
        lon: float,
        time_utc,
        duration_h: int,
        domain: str,
        vessel_type: Optional[str] = None,
        reverse: bool = False,
    ) -> DriftResult:
        import random as _random

        # Leeway coefficients per vessel type (IAMSAR Vol. III, Table C-1)
        _LEEWAY = {
            "rubber_boat":    (0.035, 20.0),  # (wind fraction, crosswind_deg_max)
            "life_raft":      (0.028, 15.0),
            "fishing_vessel": (0.018, 10.0),
            "wooden_boat":    (0.022, 12.0),
            "sailboat":       (0.014, 18.0),
            "motorboat":      (0.025, 12.0),
            "container_ship": (0.007,  8.0),
            "unknown":        (0.030, 20.0),
        }
        lw_coeff, lw_max_deg = _LEEWAY.get(vessel_type or "unknown", (0.030, 20.0))

        # Hourly forecast or mock series
        if self.mock:
            w0 = self._mock_wind(lat, lon)
            ws0 = float(w0["wind_speed_ms"])
            wd0 = float(w0["wind_dir_deg"])
            rad0 = math.radians(wd0)
            series = [{"h": h, "wind_speed_ms": ws0, "wind_dir_deg": wd0,
                        "wind_x": ws0 * math.sin(rad0), "wind_y": ws0 * math.cos(rad0)}
                      for h in range(duration_h)]
        else:
            series = self._cache.get_wind_forecast_series(lat, lon, hours=duration_h)

        # Ocean current: fixed Mediterranean baseline (CMEMS optional)
        current_u, current_v = 0.12, 0.06   # m/s east, north

        # Monte-Carlo ensemble — 40 particles
        N = 40
        rng = _random.Random(int(abs(lat) * 1e4 + abs(lon) * 1e3) % (2**31))
        cos_lat = math.cos(math.radians(lat))

        # Each particle: [lon, lat]
        particles: list[list[float]] = [[lon, lat] for _ in range(N)]
        # particle_steps[particle_idx][step] = [lon, lat]
        trails: list[list[list[float]]] = [[[lon, lat]] for _ in range(N)]

        for step_wx in series:
            ws = float(step_wx["wind_speed_ms"])
            wd_rad = math.radians(float(step_wx["wind_dir_deg"]))
            if reverse:
                wd_rad = (wd_rad + math.pi) % (2 * math.pi)

            for i, p in enumerate(particles):
                # Per-particle leeway spread: ±20% magnitude, ±crosswind_deg angle
                lw_i    = lw_coeff * (0.8 + 0.4 * rng.random())
                ang_off = math.radians(rng.uniform(-lw_max_deg, lw_max_deg))
                drift_dir = wd_rad + math.pi + ang_off   # downwind + crosswind offset

                drift_ms = ws * lw_i + math.sqrt(current_u**2 + current_v**2)
                d_km = drift_ms * 3.6  # 1-hour step → km

                c_lat = math.cos(math.radians(p[1]))
                dlat = (d_km * math.cos(drift_dir)) / 111.32
                dlon = (d_km * math.sin(drift_dir)) / (111.32 * (c_lat + 1e-9))
                p[0] += dlon
                p[1] += dlat
                trails[i].append([p[0], p[1]])

        # Mean trajectory (step 0 is origin, steps 1..N are hourly positions)
        n_steps = len(series)
        traj_coords: list[list[float]] = [[lon, lat]]
        for t in range(1, n_steps + 1):
            mean_lon = sum(trails[i][t][0] for i in range(N)) / N
            mean_lat = sum(trails[i][t][1] for i in range(N)) / N
            traj_coords.append([mean_lon, mean_lat])

        def _hull(pts: list[tuple[float, float]]) -> list[list[float]]:
            unique = sorted(set(pts))
            if len(unique) <= 2:
                return [[p[0], p[1]] for p in unique] + [[unique[0][0], unique[0][1]]]
            def cross(o, a, b):
                return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
            lower: list = []
            for p in unique:
                while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                    lower.pop()
                lower.append(p)
            upper: list = []
            for p in reversed(unique):
                while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                    upper.pop()
                upper.append(p)
            hull = lower[:-1] + upper[:-1]
            hull.append(hull[0])
            return [[p[0], p[1]] for p in hull]

        def _cone_at(hours: int) -> dict:
            idx = min(hours, n_steps)
            pts = [(trails[i][idx][0], trails[i][idx][1]) for i in range(N)]
            hull = _hull(pts)
            return {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [hull]},
                "properties": {"type": f"cone_{hours}h", "hours": hours,
                               "model": "MC-forecast", "n_particles": N},
            }

        ep = traj_coords[-1]
        return DriftResult(
            trajectory={
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": traj_coords},
                "properties": {"type": "trajectory", "model": "MC-forecast",
                               "n_particles": N, "leeway_coeff": lw_coeff},
            },
            cone_6h=_cone_at(min(6, n_steps)),
            cone_12h=_cone_at(min(12, n_steps)),
            cone_24h=_cone_at(min(24, n_steps)),
            impact_point={"type": "FeatureCollection", "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": ep},
                "properties": {"type": "impact_point", "hours": duration_h},
            }]},
            metadata={
                "domain": domain,
                "start_time": time_utc.isoformat(),
                "duration_h": duration_h,
                "model": "Monte-Carlo / Open-Meteo forecast",
                "n_particles": N,
                "leeway_coeff": round(lw_coeff, 4),
                "vessel_type": vessel_type,
                "wind_source": series[0].get("source", "open-meteo") if series else "fallback",
            },
        )


if __name__ == "__main__":
    from datetime import timezone
    engine = DriftEngine(mock=True)
    result = engine.compute(lat=35.5, lon=14.0, time_utc=datetime.now(timezone.utc))
    print("DriftEngine self-test OK:", result.metadata)
    back = engine.backtrack(lat=35.5, lon=14.0, time_utc=datetime.now(timezone.utc))
    print("Backtrack OK:", back.metadata)
    bal = engine.compute(lat=55.535, lon=15.698, time_utc=datetime.now(timezone.utc),
                         domain="ballistic")
    print("Ballistic OK:", bal.impact_point)
