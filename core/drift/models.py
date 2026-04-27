# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenDrift model wrappers and BallisticTerminal solver."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any


LEEWAY_OBJECT_TYPE: dict[str, int] = {
    "person_in_water": 26,
    "rubber_boat":     38,   # inflatable boat without canopy
    "life_raft":       27,   # canopied, 1-4 persons (29 for 5-9)
    "fishing_vessel":  52,
    "wooden_boat":     46,
    "sailboat":        26,   # no dedicated OpenDrift sail type; PIW closest
    "default":         26,
}


def resolve_object_type(vessel_type: str, persons: int = 1) -> int:
    """Map vessel_type string to OpenDrift Leeway object_type integer."""
    if vessel_type == "life_raft":
        return 27 if persons <= 4 else 29
    return LEEWAY_OBJECT_TYPE.get(vessel_type, 26)


@dataclass
class LeewayModel:
    name: str = "leeway"
    description: str = "Persons, life rafts, rubber boats — ocean leeway drift"
    domain: str = "ocean_sar"
    opendrift_class: str = "opendrift.models.leeway.Leeway"
    default_params: dict[str, Any] = field(default_factory=lambda: {
        "object_type": 26,
        "wind_drift_factor": 0.035,
        "wind_drift_depth": 0.1,
    })


@dataclass
class OpenOilModel:
    name: str = "openoil"
    description: str = "Oil spill / gas bubble plume transport"
    domain: str = "ocean_oil"
    opendrift_class: str = "opendrift.models.openoil.OpenOil"
    default_params: dict[str, Any] = field(default_factory=lambda: {
        "oil_type": "GENERIC LIGHT CRUDE",
        "do3D": True,
    })


@dataclass
class WindBlowModel:
    name: str = "windblow"
    description: str = "Atmospheric particulate, smoke, chemical plume"
    domain: str = "atmosphere"
    opendrift_class: str = "opendrift.models.windblow.WindBlow"
    default_params: dict[str, Any] = field(default_factory=lambda: {"weight": 1.0})


@dataclass
class BallisticTerminal:
    """Terminal-phase ballistic trajectory solver (no OpenDrift required)."""
    name: str = "ballistic"
    description: str = "Terminal phase ballistic projectile or drone"
    domain: str = "ballistic"
    opendrift_class: str = ""
    default_params: dict[str, Any] = field(default_factory=lambda: {
        "Cd": 0.47, "rho_air": 1.225, "g": 9.81,
    })

    def solve(
        self,
        lat: float,
        lon: float,
        entry_angle_deg: float,
        entry_velocity_ms: float,
        entry_altitude_m: float,
        mass_kg: float = 10.0,
        area_m2: float = 0.05,
        wind_speed_ms: float = 0.0,
        wind_dir_deg: float = 0.0,
    ) -> dict[str, Any]:
        """Compute impact point using Euler integration."""
        Cd = self.default_params["Cd"]
        rho = self.default_params["rho_air"]
        g = self.default_params["g"]
        k = 0.5 * Cd * rho * area_m2 / mass_kg

        angle_rad = math.radians(entry_angle_deg)
        wind_rad = math.radians(wind_dir_deg)
        vx0 = entry_velocity_ms * math.cos(angle_rad)
        vy0 = -entry_velocity_ms * math.sin(angle_rad)  # descending
        wx = wind_speed_ms * math.sin(wind_rad)

        dt, x, y, vx, vy = 0.01, 0.0, entry_altitude_m, vx0, vy0
        while y > 0 and x < 500_000:
            v_rel_x = vx - wx
            v_mag = math.sqrt(v_rel_x**2 + vy**2)
            vx += (-k * v_mag * v_rel_x) * dt
            vy += (-g - k * v_mag * vy) * dt
            x += vx * dt
            y += vy * dt

        bearing_rad = wind_rad
        cos_lat = math.cos(math.radians(lat))
        impact_lat = lat + (x * math.cos(bearing_rad)) / 111_320
        impact_lon = lon + (x * math.sin(bearing_rad)) / (111_320 * cos_lat)
        fragment_radius_m = max(50.0, x * 0.02)

        return {
            "impact": {"lat": impact_lat, "lon": impact_lon},
            "range_m": round(x),
            "fragment_radius_m": round(fragment_radius_m),
            "geojson": {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [impact_lon, impact_lat]},
                    "properties": {"type": "impact_point", "range_m": round(x),
                                   "fragment_radius_m": round(fragment_radius_m)},
                }],
            },
        }


ALL_MODELS = [LeewayModel(), OpenOilModel(), WindBlowModel(), BallisticTerminal()]

if __name__ == "__main__":
    b = BallisticTerminal()
    r = b.solve(lat=55.535, lon=15.698, entry_angle_deg=45,
                entry_velocity_ms=800, entry_altitude_m=10_000)
    print(f"BallisticTerminal self-test OK: impact={r['impact']}, range={r['range_m']}m")
