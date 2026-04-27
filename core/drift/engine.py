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
            return self._gaussian_drift(lat, lon, time_utc, duration_h, domain)
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
        payload = {
            "lat": lat, "lon": lon,
            "time_utc": time_utc.isoformat(),
            "duration_h": duration_h,
            "domain": domain,
            "environment": {
                "x_wind": float(config.get("x_wind", 0.0)),
                "y_wind": float(config.get("y_wind", 0.0)),
                "x_sea_water_velocity": float(config.get("x_sea_water_velocity", current.get("u_ms", 0.0))),
                "y_sea_water_velocity": float(config.get("y_sea_water_velocity", current.get("v_ms", 0.0))),
                "land_binary_mask": 0,
            },
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
        wind_speed = float(wind.get("wind_speed_ms", 0.0))
        wind_dir_deg = float(wind.get("wind_dir_deg", 0.0))
        wind_dir_rad = math.radians(wind_dir_deg)
        payload["environment"]["x_wind"] = float(
            config.get("x_wind", wind_speed * math.sin(wind_dir_rad))
        )
        payload["environment"]["y_wind"] = float(
            config.get("y_wind", wind_speed * math.cos(wind_dir_rad))
        )
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

    # ── Gaussian geometric fallback ─────────────────────────────────────────
    def _gaussian_drift(
        self, lat, lon, time_utc, duration_h, domain, reverse=False
    ) -> DriftResult:
        wind = self._mock_wind(lat, lon) if self.mock else self._cache.get_wind_live(lat, lon)

        # Clamp wind speed: Open-Meteo sometimes returns km/h despite ms unit param
        raw_spd = float(wind["wind_speed_ms"])
        wind_ms = min(raw_spd, 30.0) if raw_spd <= 30.0 else raw_spd / 3.6  # auto-detect km/h
        wind_ms = max(1.0, min(wind_ms, 25.0))  # cap at 25 m/s

        leeway = wind_ms * 0.035          # 3.5% leeway (SAR standard)
        current_ms = 0.15                  # Mediterranean surface current ~0.15 m/s
        total_spd_ms = leeway + current_ms # combined drift speed
        total_spd_kmh = total_spd_ms * 3.6

        dir_deg = (wind["wind_dir_deg"] + 180 + 15) % 360  # downwind + 15° leeway
        if reverse:
            dir_deg = (dir_deg + 180) % 360
        dir_rad = math.radians(dir_deg)
        cos_lat = math.cos(math.radians(lat))

        def _project(h: float, spread_deg: float = 0.0) -> list[float]:
            """Project origin by h hours along dir_rad+spread_deg."""
            d_km = total_spd_kmh * h
            ang = dir_rad + math.radians(spread_deg)
            dlat = (d_km * math.cos(ang)) / 111.32
            dlon = (d_km * math.sin(ang)) / (111.32 * cos_lat + 1e-9)
            return [lon + dlon, lat + dlat]

        # Build fan-shaped uncertainty cone (sector / pie-slice)
        # Angular spread grows with time: ±10° at 6h, ±18° at 12h, ±28° at 24h
        def cone(h: float, half_angle: float) -> dict:
            n_arc = 20
            pts: list[list[float]] = [[lon, lat]]
            for i in range(n_arc + 1):
                frac = i / n_arc
                angle_off = -half_angle + 2 * half_angle * frac
                pts.append(_project(h, angle_off))
            pts.append([lon, lat])  # close polygon
            return {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [pts]},
                "properties": {"hours": h, "half_angle_deg": half_angle,
                               "drift_speed_ms": round(total_spd_ms, 3)},
            }

        # Multi-waypoint trajectory with small random walk for realism
        n_steps = max(8, duration_h)
        traj_coords: list[list[float]] = [[lon, lat]]
        rng_seed = int(lat * 1000 + lon * 100) % 999
        for step in range(1, n_steps + 1):
            h = duration_h * step / n_steps
            # Add small sinusoidal meander
            meander = math.sin(step * 0.9 + rng_seed) * 0.3
            pt = _project(h, meander)
            traj_coords.append(pt)

        traj = {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": traj_coords},
            "properties": {"type": "trajectory", "n_steps": n_steps},
        }

        # Final predicted position
        ep = traj_coords[-1]
        impact = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": ep},
            "properties": {"type": "trajectory", "hours": duration_h},
        }

        return DriftResult(
            trajectory=traj,
            cone_6h=cone(6, 10.0),
            cone_12h=cone(12, 18.0),
            cone_24h=cone(24, 28.0),
            impact_point={"type": "FeatureCollection", "features": [impact]},
            metadata={
                "domain": domain,
                "start_time": time_utc.isoformat(),
                "duration_h": duration_h,
                "model": "Gaussian fallback",
                "wind_speed_ms": round(wind_ms, 2),
                "wind_dir_deg": wind["wind_dir_deg"],
                "drift_speed_ms": round(total_spd_ms, 3),
                "drift_dir_deg": round(dir_deg, 1),
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
