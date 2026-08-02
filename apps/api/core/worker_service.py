# SPDX-License-Identifier: AGPL-3.0-or-later
"""Standalone drift-compute worker — no DB, no intel engine, no auth stack.

Runs on a dedicated free-tier VM so the heavy OpenDrift/CMEMS numeric work
never competes with the always-on API/intel-monitor process for RAM on a
1 GB box. The main API calls this over the network when DRIFT_WORKER_URL is
set (see core.drift.remote); otherwise DriftEngine still runs in-process,
so this is purely additive — nothing breaks if the worker is unreachable
or not configured.

Protected by a shared secret header rather than the full auth stack: this
process has no user accounts, no database, and exposes exactly one action
(run a bounded drift simulation), so a bearer-style shared secret is
proportionate rather than pulling in Keycloak/OIDC for a single internal
service-to-service call.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="SeaCommons Drift Worker")

_SECRET = os.environ.get("DRIFT_WORKER_SECRET", "")


class ComputeRequest(BaseModel):
    lat: float
    lon: float
    time_utc: str
    duration_h: int = 24
    domain: str = "ocean_sar"
    config: Optional[dict[str, Any]] = None
    backtrack: bool = False


def _check_secret(x_worker_secret: Optional[str]) -> None:
    if not _SECRET:
        raise HTTPException(status_code=503, detail="DRIFT_WORKER_SECRET not configured")
    if x_worker_secret != _SECRET:
        raise HTTPException(status_code=403, detail="Invalid worker secret")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "role": "drift-worker"}


@app.post("/compute")
def compute(body: ComputeRequest, x_worker_secret: Optional[str] = Header(None)) -> dict[str, Any]:
    _check_secret(x_worker_secret)
    from core.drift.engine import DriftEngine

    engine = DriftEngine()
    time_utc = datetime.fromisoformat(body.time_utc)
    try:
        if body.backtrack:
            result = engine.backtrack(
                lat=body.lat, lon=body.lon, time_utc=time_utc,
                duration_h=body.duration_h, domain=body.domain, config=body.config,
            )
        else:
            result = engine.compute(
                lat=body.lat, lon=body.lon, time_utc=time_utc,
                duration_h=body.duration_h, domain=body.domain, config=body.config,
            )
    except Exception as exc:
        logger.exception("Drift worker compute failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result.model_dump()
