# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operational summary endpoints for the Seacommons dashboard."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from core.config import config
from core.db.store import list_alerts, list_forensic_packets
from core.integrations.store import IntegrationEventStore
from core.integrations.timezero import timezero_health
from core.vessels.registry import registry

router = APIRouter()

_integration_store = IntegrationEventStore()
@router.get("/api/v1/ops/summary")
async def ops_summary():
    recent_raw_events = _integration_store.recent(limit=50)
    vessel_stats = registry.stats()
    alerts = list_alerts()
    forensic_packets = list_forensic_packets()

    recent_events = []
    for event in recent_raw_events[:12]:
        payload = event.get("payload") or {}
        recent_events.append(
            {
                "timestamp": event.get("timestamp"),
                "event_type": event.get("event_type"),
                "status": event.get("status"),
                "adapter": ((event.get("source") or {}).get("adapter") if isinstance(event.get("source"), dict) else None),
                "protocol": ((event.get("source") or {}).get("protocol") if isinstance(event.get("source"), dict) else None),
                "vessel_id": ((event.get("source") or {}).get("vessel_id") if isinstance(event.get("source"), dict) else None),
                "ship_name": payload.get("ship_name"),
                "lat": event.get("lat"),
                "lon": event.get("lon"),
            }
        )

    return {
        "product": {
            "name": "Seacommons",
            "mode": "pilot",
            "role": "operational_sar",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend": {
            "mock": config.MOCK,
            "database": "sqlite" if config.DATABASE_URL.startswith("sqlite") else "postgres",
            "redis_configured": bool(config.REDIS_URL),
            "aisstream_live": bool(config.AISSTREAM_KEY) and not config.MOCK,
            "cmems_live": bool(config.CMEMS_USERNAME and config.CMEMS_PASSWORD) and not config.MOCK,
            "timezero": timezero_health(),
        },
        "signals": {
            "recent_event_count": len(recent_raw_events),
            "recent_events": recent_events,
        },
        "traffic": {
            "registry": vessel_stats,
        },
        "sar": {
            "open_alerts": sum(1 for alert in alerts if alert.get("status") != "completed"),
            "completed_alerts": sum(1 for alert in alerts if alert.get("status") == "completed"),
            "forensic_packets": len(forensic_packets),
        },
        "cost_profile": {
            "frontend": "static_vite",
            "backend": "fastapi_polling",
            "state_store": "sqlite_or_postgres",
            "queue": "optional",
        },
    }
