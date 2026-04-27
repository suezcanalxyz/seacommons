# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drift computation endpoints."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

router = APIRouter()


class DriftRequest(BaseModel):
    lat: float
    lon: float
    timestamp: Optional[datetime] = None
    duration_h: int = 24
    domain: str = "ocean_sar"
    config: dict = {}


def _run_drift(drift_id: str, req: DriftRequest) -> None:
    from core.db.store import complete_drift_job, fail_drift_job
    from core.drift.engine import DriftEngine

    engine = DriftEngine()
    ts = req.timestamp or datetime.utcnow()

    try:
        result = engine.compute(
            lat=req.lat,
            lon=req.lon,
            time_utc=ts,
            duration_h=req.duration_h,
            domain=req.domain,
            config=req.config,
        )
        complete_drift_job(
            drift_id,
            event_id=None,
            lat=req.lat,
            lon=req.lon,
            domain=req.domain,
            result=result,
        )

        try:
            from core.integrations.timezero import push_drift_to_timezero

            push_drift_to_timezero(
                drift_id=drift_id,
                result=result,
                origin_lat=req.lat,
                origin_lon=req.lon,
                label="API Drift",
            )
        except Exception as exc:
            logging.getLogger(__name__).warning("TimeZero bridge error: %s", exc)
    except Exception as exc:
        logging.getLogger(__name__).error("Drift failed for %s: %s", drift_id, exc)
        fail_drift_job(
            drift_id,
            event_id=None,
            lat=req.lat,
            lon=req.lon,
            domain=req.domain,
            error_message=str(exc),
        )


@router.post("/api/v1/drift")
async def create_drift(req: DriftRequest, bg: BackgroundTasks):
    from core.db.store import create_drift_job

    drift_id = str(uuid.uuid4())
    create_drift_job(
        drift_id,
        event_id=None,
        lat=req.lat,
        lon=req.lon,
        domain=req.domain,
        duration_h=req.duration_h,
        started_at=req.timestamp or datetime.utcnow(),
    )
    bg.add_task(_run_drift, drift_id, req)
    return {"drift_id": drift_id, "status": "computing"}


@router.get("/api/v1/drift/{drift_id}/geojson")
async def get_drift_geojson(drift_id: str):
    from core.db.store import get_drift

    result = get_drift(drift_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Drift ID not found")
    if result.get("status") == "computing":
        raise HTTPException(status_code=202, detail="Still computing")
    if result.get("status") == "failed":
        raise HTTPException(
            status_code=500,
            detail=result.get("metadata", {}).get("error", "Drift failed"),
        )

    features = [result["trajectory"], result["cone_6h"], result["cone_12h"], result["cone_24h"]]
    if result["impact_point"]:
        features.extend(result["impact_point"].get("features", []))
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": result["metadata"],
    }
