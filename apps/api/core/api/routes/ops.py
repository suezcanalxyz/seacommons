# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operational summary endpoints for the Seacommons dashboard."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter

from core.config import config
from core.vessels.aisstream import get_client
from core.vessels.registry import registry

router = APIRouter()


@router.get("/api/v1/ops/summary")
async def ops_summary():
    """
    Fast summary for the dashboard banner.
    No DB calls — uses only in-memory state so it always responds in <100ms.
    Heavy stats (alerts, forensic packets) are available via their own endpoints.
    """
    loop = asyncio.get_event_loop()

    # TimeZero health — only checked if explicitly enabled, max 1s
    if config.TIMEZERO_ENABLED:
        try:
            from core.integrations.timezero import timezero_health
            _tz_status = await asyncio.wait_for(
                loop.run_in_executor(None, timezero_health), timeout=1.0
            )
        except Exception:
            _tz_status = {"enabled": True, "reachable": False, "host": config.TIMEZERO_HOST, "port": config.TIMEZERO_PORT}
    else:
        _tz_status = {"enabled": False, "reachable": None, "host": "—", "port": 4371}

    # AIS client — in-memory, instant
    ais_client = get_client()
    ais_connected = bool(ais_client.connected) if ais_client else False
    ais_messages = int(ais_client.messages_received) if ais_client else 0

    # Vessel registry — in-memory, instant
    vessel_stats = registry.stats()

    # Scheduler status — in-memory, instant
    try:
        from core.scheduler import status as scheduler_status
        sched = scheduler_status()
    except Exception:
        sched = {"running": False, "jobs": []}

    return {
        "product": {
            "name": "Seacommons",
            "mode": config.RUNTIME_PROFILE,
            "role": "operational_sar",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend": {
            "runtime_profile": config.RUNTIME_PROFILE,
            "database": "sqlite" if config.DATABASE_URL.startswith("sqlite") else "postgres",
            "redis_configured": bool(config.REDIS_URL),
            "aisstream_configured": bool(config.AISSTREAM_KEY),
            "aisstream_connected": ais_connected,
            "aisstream_messages": ais_messages,
            "cmems_configured": bool(config.CMEMS_USERNAME and config.CMEMS_PASSWORD),
            "timezero": _tz_status,
        },
        "traffic": {
            "registry": vessel_stats,
        },
        "scheduler": sched,
        "cost_profile": {
            "frontend": "static_vite",
            "backend": "fastapi_polling",
            "state_store": "sqlite_or_postgres",
            "queue": "optional",
        },
    }


@router.get("/api/v1/ops/stats")
async def ops_stats():
    """
    Heavier stats (DB-backed): alert counts, forensic packets, recent events.
    Polled separately on a longer interval — not needed for initial page load.
    """
    loop = asyncio.get_event_loop()

    try:
        from core.db.store import list_alerts, list_forensic_packets
        alerts, forensic_packets = await asyncio.wait_for(
            asyncio.gather(
                loop.run_in_executor(None, list_alerts),
                loop.run_in_executor(None, list_forensic_packets),
            ),
            timeout=6.0,
        )
    except Exception:
        alerts, forensic_packets = [], []

    try:
        from core.integrations.store import IntegrationEventStore
        store = IntegrationEventStore()
        recent_raw = store.recent(limit=12)
    except Exception:
        recent_raw = []

    recent_events = []
    for event in recent_raw:
        payload = event.get("payload") or {}
        recent_events.append({
            "timestamp": event.get("timestamp"),
            "event_type": event.get("event_type"),
            "status": event.get("status"),
            "ship_name": payload.get("ship_name"),
            "lat": event.get("lat"),
            "lon": event.get("lon"),
        })

    return {
        "sar": {
            "open_alerts": sum(1 for a in alerts if a.get("status") != "completed"),
            "completed_alerts": sum(1 for a in alerts if a.get("status") == "completed"),
            "forensic_packets": len(forensic_packets),
        },
        "signals": {
            "recent_event_count": len(recent_raw),
            "recent_events": recent_events,
        },
    }
