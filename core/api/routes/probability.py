# SPDX-License-Identifier: AGPL-3.0-or-later
"""Probability API routes — survival, interception, scored signals."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.probability.engine import ProbabilityEngine, _default_assets
from core.probability.interception import Asset, compute_interception
from core.probability.survival import (
    SurvivalContext, compute_survival_probability, urgency_label,
)
from core.probability.updater import EnvironmentUpdater

router = APIRouter(prefix="/api/v1/probability", tags=["probability"])

# Module-level engine and updater singletons
_engine   = ProbabilityEngine()
_updater  = EnvironmentUpdater(_engine)
_updater.start()


# ── Request / Response models ──────────────────────────────────────────────────

class SurvivalRequest(BaseModel):
    water_temp_c: float
    air_temp_c: float
    wind_speed_ms: float
    wave_height_m: float
    persons: int = 1
    vessel_condition: Optional[str] = None
    medical_emergency: bool = False
    children_aboard: bool = False
    hours_elapsed: float = 0.0


class SurvivalResponse(BaseModel):
    survival_probability: float
    urgency: str
    hours_elapsed: float


class InterceptionRequest(BaseModel):
    distress_lat: float
    distress_lon: float
    drift_speed_kn: float = 1.5
    drift_heading_deg: float = 0.0
    survival_window_h: float = 12.0


class IngestRequest(BaseModel):
    signal_id: str


class EnvUpdate(BaseModel):
    water_temp_c: Optional[float] = None
    air_temp_c: Optional[float] = None
    wind_speed_ms: Optional[float] = None
    wave_height_m: Optional[float] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/survival", response_model=SurvivalResponse)
async def survival_probability(req: SurvivalRequest) -> SurvivalResponse:
    """Compute survival probability for given environmental conditions."""
    ctx = SurvivalContext(**req.model_dump())
    prob = compute_survival_probability(ctx)
    return SurvivalResponse(
        survival_probability=round(prob, 4),
        urgency=urgency_label(prob),
        hours_elapsed=req.hours_elapsed,
    )


@router.post("/interception", response_model=list[dict])
async def interception(req: InterceptionRequest) -> list[dict]:
    """Compute time-to-intercept for all known SAR assets."""
    assets = _engine._assets  # noqa: SLF001
    results = compute_interception(
        distress_lat=req.distress_lat,
        distress_lon=req.distress_lon,
        drift_speed_kn=req.drift_speed_kn,
        drift_heading_deg=req.drift_heading_deg,
        assets=assets,
        survival_window_h=req.survival_window_h,
    )
    return [
        {
            "asset_id": r.asset_id,
            "distance_nm": r.distance_nm,
            "time_to_intercept_h": r.time_to_intercept_h,
            "intercept_lat": r.intercept_lat,
            "intercept_lon": r.intercept_lon,
            "heading_deg": r.heading_deg,
            "feasible": r.feasible,
        }
        for r in results
    ]


@router.get("/active", response_model=list[dict])
async def active_signals() -> list[dict]:
    """Return all active scored distress signals, highest priority first."""
    scored = _engine.get_active()
    return [
        {
            "signal_id": s.signal.signal_id,
            "source_channel": s.signal.source_channel,
            "lat": s.signal.lat,
            "lon": s.signal.lon,
            "persons": s.signal.persons,
            "survival_probability": s.survival_prob,
            "urgency": s.urgency,
            "priority_score": s.priority_score,
            "nearest_asset_h": s.nearest_asset_h,
            "extraction_confidence": s.signal.extraction_confidence,
            "requires_human_review": s.signal.requires_human_review,
        }
        for s in scored
    ]


@router.post("/ingest/{signal_id}", response_model=dict)
async def ingest_signal_to_engine(signal_id: str) -> dict:
    """
    Promote an already-ingested DistressSignal into the probability engine.
    Looks up the signal from the ingestion store by ID.
    """
    from core.ingestion import router as ingest_router
    signals = ingest_router.load_recent(limit=500)
    sig = next((s for s in signals if s.signal_id == signal_id), None)
    if sig is None:
        raise HTTPException(status_code=404, detail="Signal not found in ingestion store")
    scored = _engine.ingest(sig)
    return {
        "signal_id": signal_id,
        "urgency": scored.urgency,
        "priority_score": scored.priority_score,
        "survival_probability": scored.survival_prob,
    }


@router.delete("/active/{signal_id}", response_model=dict)
async def resolve_signal(signal_id: str) -> dict:
    """Mark a signal as resolved and remove from active scoring."""
    removed = _engine.resolve(signal_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Signal not found in active set")
    return {"status": "resolved", "signal_id": signal_id}


@router.post("/environment", response_model=dict)
async def update_environment(env: EnvUpdate) -> dict:
    """Manually push updated environmental conditions to the engine."""
    _engine.update_environment(**env.model_dump(exclude_none=True))
    data = _updater.fetch_now()
    return {"status": "updated", "current": data}


@router.get("/environment", response_model=dict)
async def get_environment() -> dict:
    """Return current environmental conditions from the updater."""
    return _updater.fetch_now()
