# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Survival probability models.

References:
- Golden 1976: immersion survival time tables
- Tikuisis 1997: rectal temperature prediction model
- IMO IAMSAR Manual Vol. III, 2022 edition
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SurvivalContext:
    """All factors that affect survival probability."""
    water_temp_c: float           # Sea surface temperature (Celsius)
    air_temp_c: float             # Air temperature (Celsius)
    wind_speed_ms: float          # Wind speed (m/s)
    wave_height_m: float          # Significant wave height (m)
    persons: int = 1              # Number of persons in distress
    vessel_condition: Optional[str] = None   # sinking | taking_water | engine_failure | None
    medical_emergency: bool = False
    children_aboard: bool = False
    hours_elapsed: float = 0.0   # Hours since distress signal received


# ── Golden 1976 lookup table (water_temp_c → expected survival hours) ─────────
# Simplified: 50th-percentile survival time for unprotected immersion
_GOLDEN_TABLE: list[tuple[float, float]] = [
    (0.0,  0.5),
    (5.0,  1.0),
    (10.0, 2.0),
    (15.0, 6.0),
    (20.0, 12.0),
    (25.0, 24.0),
    (30.0, 40.0),
]


def _golden_survival_hours(water_temp_c: float) -> float:
    """Interpolate Golden 1976 survival time (hours) from water temperature."""
    temp = max(0.0, min(water_temp_c, 30.0))
    for i in range(len(_GOLDEN_TABLE) - 1):
        t0, h0 = _GOLDEN_TABLE[i]
        t1, h1 = _GOLDEN_TABLE[i + 1]
        if t0 <= temp <= t1:
            frac = (temp - t0) / (t1 - t0)
            return h0 + frac * (h1 - h0)
    return _GOLDEN_TABLE[-1][1]


def _tikuisis_cooling_rate(water_temp_c: float, wind_speed_ms: float) -> float:
    """
    Tikuisis 1997: simplified body cooling rate (°C / hour).
    Based on convective + conductive heat loss in cold water.
    """
    delta_t = 37.0 - water_temp_c          # core–water temperature gradient
    # Wind effect on surface cooling (spray exposure)
    wind_factor = 1.0 + 0.03 * wind_speed_ms
    return 0.25 * delta_t * wind_factor / 10.0  # normalised


def compute_survival_probability(ctx: SurvivalContext) -> float:
    """
    Return a survival probability in [0.0, 1.0] for a distress situation.

    The model is:
    1. Base survival time from Golden 1976 (water temperature)
    2. Penalise for wind chill, wave exposure
    3. Penalise for condition (sinking = faster deterioration)
    4. Penalise for medical emergency / children
    5. Exponential decay over elapsed time
    """
    base_hours = _golden_survival_hours(ctx.water_temp_c)

    # Wind chill reduces effective survival time
    cooling = _tikuisis_cooling_rate(ctx.water_temp_c, ctx.wind_speed_ms)
    wave_factor = max(0.5, 1.0 - 0.05 * ctx.wave_height_m)
    effective_hours = base_hours * wave_factor / max(0.1, 1.0 + cooling)

    # Vessel condition penalty
    if ctx.vessel_condition == "sinking":
        effective_hours *= 0.40
    elif ctx.vessel_condition == "taking_water":
        effective_hours *= 0.65
    elif ctx.vessel_condition == "engine_failure":
        effective_hours *= 0.85

    # Vulnerability multipliers
    if ctx.medical_emergency:
        effective_hours *= 0.70
    if ctx.children_aboard:
        effective_hours *= 0.80

    # Exponential survival decay: P(t) = exp(-t / T)
    if effective_hours <= 0:
        return 0.0
    prob = math.exp(-ctx.hours_elapsed / effective_hours)
    return max(0.0, min(1.0, prob))


def urgency_label(survival_prob: float) -> str:
    """Human-readable urgency from survival probability."""
    if survival_prob >= 0.80:
        return "ROUTINE"
    if survival_prob >= 0.50:
        return "ELEVATED"
    if survival_prob >= 0.20:
        return "URGENT"
    return "IMMEDIATE"
