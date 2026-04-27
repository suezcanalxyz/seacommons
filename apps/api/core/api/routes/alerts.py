# SPDX-License-Identifier: AGPL-3.0-or-later
"""Maritime distress alert endpoints."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket
from pydantic import BaseModel

router = APIRouter()


class MaritimeEvent(BaseModel):
    lat: float
    lon: float
    timestamp: datetime
    persons: Optional[int] = None
    vessel_type: Optional[str] = None
    domain: str = "ocean_sar"


active_ws: list[WebSocket] = []


def _process_drift(event_id: str, event: MaritimeEvent) -> None:
    from core.db.store import complete_drift_job, fail_drift_job, update_alert_status
    from core.drift.engine import DriftEngine
    from core.forensic.logger import sign_and_broadcast

    engine = DriftEngine()
    status = "completed"
    try:
        alert_config: dict = {}
        if event.vessel_type:
            alert_config["vessel_type"] = event.vessel_type
        if event.persons is not None:
            alert_config["persons"] = event.persons
        result = engine.compute(
            lat=event.lat,
            lon=event.lon,
            time_utc=event.timestamp,
            duration_h=48,
            domain=event.domain,
            config=alert_config,
        )
        complete_drift_job(
            event_id,
            event_id=event_id,
            lat=event.lat,
            lon=event.lon,
            domain=event.domain,
            result=result,
        )

        try:
            from core.integrations.timezero import push_drift_to_timezero

            push_drift_to_timezero(
                drift_id=event_id,
                result=result,
                origin_lat=event.lat,
                origin_lon=event.lon,
                label="SAR Alert",
            )
        except Exception as exc:
            logging.getLogger(__name__).warning("TimeZero bridge error: %s", exc)

        sign_and_broadcast(
            event_id,
            event.model_dump(mode="json"),
            result.model_dump(),
            position={"lat": event.lat, "lon": event.lon, "alt": 0, "source": "alert"},
            classification="sar_distress",
            confidence=0.9,
        )
    except Exception as exc:
        status = "failed"
        logging.getLogger(__name__).error("Alert drift failed for %s: %s", event_id, exc)
        fail_drift_job(
            event_id,
            event_id=event_id,
            lat=event.lat,
            lon=event.lon,
            domain=event.domain,
            error_message=str(exc),
        )

    update_alert_status(event_id, status)
    payload = {"event_id": event_id, "status": status}
    for ws in list(active_ws):
        try:
            asyncio.run(ws.send_text(json.dumps(payload)))
        except Exception:
            active_ws.remove(ws)


@router.post("/api/v1/alert")
async def create_alert(event: MaritimeEvent, bg: BackgroundTasks):
    from core.db.store import create_alert, create_drift_job

    event_id = str(uuid.uuid4())
    create_alert(event_id, event, status="processing")
    create_drift_job(
        event_id,
        event_id=event_id,
        lat=event.lat,
        lon=event.lon,
        domain=event.domain,
        duration_h=48,
        started_at=event.timestamp,
    )
    bg.add_task(_process_drift, event_id, event)
    return {"event_id": event_id, "status": "processing"}


@router.get("/api/v1/alert/{event_id}")
async def get_alert(event_id: str):
    from core.db.store import get_alert

    payload = get_alert(event_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return payload


@router.get("/api/v1/alert/{event_id}/geojson")
async def get_alert_geojson(event_id: str):
    from core.db.store import get_drift

    drift = get_drift(event_id)
    if drift is None:
        raise HTTPException(status_code=404, detail="Drift result not ready")
    if drift.get("status") == "computing":
        raise HTTPException(status_code=202, detail="Drift result not ready")
    if drift.get("status") == "failed":
        raise HTTPException(
            status_code=500,
            detail=drift.get("metadata", {}).get("error", "Drift result failed"),
        )
    if drift.get("status") != "completed":
        raise HTTPException(status_code=404, detail="Drift result not ready")

    features = [drift["trajectory"], drift["cone_6h"], drift["cone_12h"], drift["cone_24h"]]
    if drift["impact_point"]:
        features.extend(drift["impact_point"].get("features", []))
    return {"type": "FeatureCollection", "features": features}


@router.get("/api/v1/alerts")
async def list_alerts():
    from core.db.store import list_alerts

    return list_alerts()


@router.get("/api/v1/alerts/geojson")
async def list_alerts_geojson():
    from core.db.store import get_drift, list_alerts

    features = []
    for alert in list_alerts():
        drift = get_drift(alert["event_id"])
        if drift is None or drift.get("status") != "completed":
            continue
        features.extend([drift["trajectory"], drift["cone_6h"], drift["cone_12h"], drift["cone_24h"]])
    return {"type": "FeatureCollection", "features": features}


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await websocket.accept()
    active_ws.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        if websocket in active_ws:
            active_ws.remove(websocket)
