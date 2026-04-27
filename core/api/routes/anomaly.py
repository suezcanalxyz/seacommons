# SPDX-License-Identifier: AGPL-3.0-or-later
"""Anomaly query endpoints — REST + WebSocket stream."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query, WebSocket

router = APIRouter()

# In-memory ring buffer (last 10k anomalies)
_anomalies: list[dict] = []
_MAX = 10_000


def ingest_anomaly(event: dict) -> None:
    """Called by sensor threads to store anomalies."""
    global _anomalies
    _anomalies.append(event)
    if len(_anomalies) > _MAX:
        _anomalies = _anomalies[-_MAX:]


@router.get("/api/v1/anomalies")
async def list_anomalies(
    since_minutes: int = Query(default=60),
    type: str = Query(default="all"),
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None),
    radius_km: Optional[float] = Query(default=None),
):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    result = []
    for ev in reversed(_anomalies):
        try:
            ts = datetime.fromisoformat(ev.get("timestamp_utc", "").replace("Z", "+00:00"))
            if ts < cutoff:
                continue
        except Exception:
            continue
        if type != "all" and ev.get("anomaly_type", ev.get("source", "")) != type:
            continue
        if lat is not None and lon is not None and radius_km is not None:
            import math
            elat = ev.get("lat", ev.get("position", {}).get("lat", None))
            elon = ev.get("lon", ev.get("position", {}).get("lon", None))
            if elat is not None and elon is not None:
                dist = math.sqrt((lat - elat)**2 + (lon - elon)**2) * 111
                if dist > radius_km:
                    continue
        result.append(ev)
    result.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return {"count": len(result), "anomalies": result}


_ws_clients: list[WebSocket] = []


@router.websocket("/api/v1/anomalies/live")
async def anomaly_live(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


async def broadcast_anomaly(event: dict) -> None:
    """Broadcast to all live anomaly WebSocket clients."""
    import asyncio
    ingest_anomaly(event)
    for ws in list(_ws_clients):
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            _ws_clients.remove(ws)
