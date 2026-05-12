# SPDX-License-Identifier: AGPL-3.0-or-later
"""Maritime distress alert endpoints."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket
from pydantic import BaseModel

from core.config import config

router = APIRouter()
logger = logging.getLogger(__name__)


class MaritimeEvent(BaseModel):
    lat: float
    lon: float
    timestamp: datetime
    persons: Optional[int] = None
    vessel_type: Optional[str] = None
    risk_level: Optional[str] = None
    scenario_type: Optional[str] = None
    domain: str = "ocean_sar"


# (websocket, asyncio_loop) — stored as tuples so background threads can
# safely schedule sends via asyncio.run_coroutine_threadsafe()
active_ws: list[tuple[WebSocket, asyncio.AbstractEventLoop]] = []
_ws_lock = threading.Lock()


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
        if event.risk_level:
            alert_config["risk_level"] = event.risk_level
        if event.scenario_type:
            alert_config["scenario_type"] = event.scenario_type
        result = engine.compute(
            lat=event.lat,
            lon=event.lon,
            time_utc=event.timestamp,
            duration_h=config.ALERT_DRIFT_DURATION_H,
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
    _broadcast_ws({"event_id": event_id, "status": status})


def _broadcast_ws(payload: dict) -> None:
    """Thread-safe broadcast to all connected alert WebSocket clients."""
    text = json.dumps(payload)
    dead: list[tuple] = []
    with _ws_lock:
        clients = list(active_ws)
    for ws, loop in clients:
        try:
            asyncio.run_coroutine_threadsafe(_ws_send(ws, text), loop)
        except Exception:
            dead.append((ws, loop))
    if dead:
        with _ws_lock:
            for item in dead:
                try:
                    active_ws.remove(item)
                except ValueError:
                    pass


async def _ws_send(ws: WebSocket, text: str) -> None:
    try:
        await ws.send_text(text)
    except Exception:
        pass


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
        duration_h=config.ALERT_DRIFT_DURATION_H,
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
    loop = asyncio.get_event_loop()
    entry = (websocket, loop)
    with _ws_lock:
        active_ws.append(entry)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_text('{"type":"ping"}')
    except Exception:
        pass
    finally:
        with _ws_lock:
            try:
                active_ws.remove(entry)
            except ValueError:
                pass
