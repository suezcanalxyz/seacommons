# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Signal scorer — combines extraction confidence, survival probability,
and interception feasibility into a single priority score.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.ingestion.signal import DistressSignal
from core.probability.survival import SurvivalContext, compute_survival_probability, urgency_label
from core.probability.interception import Asset, InterceptionResult, compute_interception


@dataclass
class ScoredSignal:
    signal: DistressSignal
    survival_prob: float
    urgency: str                          # ROUTINE | ELEVATED | URGENT | IMMEDIATE
    priority_score: float                 # 0.0–1.0 (higher = act sooner)
    interception_results: list[InterceptionResult]
    nearest_asset_h: Optional[float]      # hours to nearest feasible asset


def score_signal(
    signal: DistressSignal,
    ctx: SurvivalContext,
    assets: list[Asset],
    drift_speed_kn: float = 1.5,
    drift_heading_deg: float = 0.0,
) -> ScoredSignal:
    """
    Compute a composite priority score for a distress signal.

    Priority = w1 * extraction_confidence
             + w2 * (1 - survival_prob)     # lower survival → higher urgency
             + w3 * interception_feasibility_bonus
    """
    survival = compute_survival_probability(ctx)
    survival_window = _survival_window_h(ctx)

    interceptions: list[InterceptionResult] = []
    if signal.lat is not None and signal.lon is not None and assets:
        interceptions = compute_interception(
            distress_lat=signal.lat,
            distress_lon=signal.lon,
            drift_speed_kn=drift_speed_kn,
            drift_heading_deg=drift_heading_deg,
            assets=assets,
            survival_window_h=survival_window,
        )

    nearest_h: Optional[float] = None
    feasibility_bonus = 0.0
    feasible = [r for r in interceptions if r.feasible]
    if feasible:
        nearest_h = feasible[0].time_to_intercept_h
        # Bonus if we can reach them within half the survival window
        if nearest_h <= survival_window * 0.5:
            feasibility_bonus = 0.10

    # Weights
    w1, w2, w3 = 0.35, 0.50, 0.15
    priority = (
        w1 * signal.extraction_confidence
        + w2 * (1.0 - survival)
        + w3 * feasibility_bonus
    )
    priority = max(0.0, min(1.0, priority))

    return ScoredSignal(
        signal=signal,
        survival_prob=round(survival, 4),
        urgency=urgency_label(survival),
        priority_score=round(priority, 4),
        interception_results=interceptions,
        nearest_asset_h=round(nearest_h, 2) if nearest_h is not None else None,
    )


def _survival_window_h(ctx: SurvivalContext) -> float:
    """Rough survival window ceiling (hours) for feasibility check."""
    from core.probability.survival import _golden_survival_hours
    return _golden_survival_hours(ctx.water_temp_c) * 1.5
