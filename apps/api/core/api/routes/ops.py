# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operational summary endpoints for the Seacommons dashboard."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import Response

from core.config import config
from core.vessels.aisstream import get_client, get_ngo_client
from core.vessels.registry import registry

router = APIRouter()


def _image_ocr_status() -> dict:
    """Whether the image-coordinate OCR pipeline can actually run.

    Alarm Phone posts the precise position as a map screenshot, not text.
    If tesseract or Pillow is missing on the host, every such coordinate is
    silently lost -- this surfaces that instead of it being invisible.
    """
    import importlib.util
    import shutil

    tesseract = shutil.which("tesseract")
    try:
        import PIL  # noqa: F401

        pillow = True
    except Exception:
        pillow = False
    try:
        import numpy  # noqa: F401

        has_numpy = True
    except Exception:
        has_numpy = False
    # Do not import Torch on every status poll.  EasyOCR's full import is
    # intentionally heavy on ARM CPU hosts and can transiently fail while a
    # recognition job has the model loaded.  The worker performs the real
    # import when OCR is requested; status reports whether that installed
    # engine is discoverable in this exact interpreter environment.
    easyocr_available = importlib.util.find_spec("easyocr") is not None
    return {
        "available": pillow and (easyocr_available or bool(tesseract)),
        "primary_engine": "easyocr" if easyocr_available else "tesseract" if tesseract else None,
        "easyocr": easyocr_available,
        "tesseract": bool(tesseract),
        "tesseract_path": tesseract or None,
        "pillow": pillow,
        "numpy": has_numpy,
    }


def _intel_monitor_status() -> dict:
    """Which intel monitors are attached in this process. In a split
    deployment they run on the intel worker, not here -- an all-false result
    with INTEL_MONITORS_ENABLED=false is expected; all-false with it true
    means the engine did not start."""
    try:
        from core.intel.engine import intel_engine

        return {"monitors_enabled": bool(config.INTEL_MONITORS_ENABLED), **intel_engine.status()}
    except Exception:
        return {"monitors_enabled": bool(config.INTEL_MONITORS_ENABLED), "running": False}


_stats_cache: bytes | None = None
_stats_cache_ts: float = 0.0
_STATS_TTL = 30.0


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
    ngo_ais_client = get_ngo_client()
    ngo_ais_connected = bool(ngo_ais_client.connected) if ngo_ais_client else False
    ngo_ais_messages = int(ngo_ais_client.messages_received) if ngo_ais_client else 0

    try:
        from core.connectors.service import status_counts
        from core.db.session import session_scope
        with session_scope() as db:
            whatsapp_connectors = status_counts(db, "whatsapp_cloud")
    except Exception:
        whatsapp_connectors = {}

    # Vessel registry — in-memory, instant
    vessel_stats = registry.stats()

    try:
        from core.radio.runtime import get_remote_radio_status

        remote_radio = get_remote_radio_status()
    except Exception:
        remote_radio = {
            "enabled": bool(config.REMOTE_RADIO_ENABLED),
            "configured": 0,
            "runnable": 0,
            "started": 0,
            "failed": 0,
            "providers": {},
        }

    # Scheduler status — in-memory, instant
    try:
        from core.scheduler import status as scheduler_status
        sched = scheduler_status()
    except Exception:
        sched = {"running": False, "jobs": []}

    # Best-effort SAR counters for backward compatibility with older UI/test callers.
    # Keep the timeout tight so this summary endpoint stays responsive even if the DB stalls.
    try:
        from core.db.store import list_alerts, list_forensic_packets
        alerts, forensic_packets = await asyncio.wait_for(
            asyncio.gather(
                loop.run_in_executor(None, list_alerts),
                loop.run_in_executor(None, list_forensic_packets),
            ),
            timeout=0.75,
        )
    except Exception:
        alerts, forensic_packets = [], []

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
            "aisstream_ngo_fleet_connected": ngo_ais_connected,
            "aisstream_ngo_fleet_messages": ngo_ais_messages,
            "cmems_configured": bool(config.CMEMS_USERNAME and config.CMEMS_PASSWORD),
            "timezero": _tz_status,
            "job_execution_mode": config.JOB_EXECUTION_MODE,
            "image_ocr": _image_ocr_status(),
            "intel_monitors": _intel_monitor_status(),
            "remote_radio": remote_radio,
        },
        "channels": {
            "twitter": {
                "configured": bool(config.TWITTER_BEARER_TOKEN),
                "transport": "official_x_api",
            },
            "whatsapp": {
                "configured": bool(
                    config.META_APP_ID
                    and config.META_APP_SECRET
                    and config.META_WEBHOOK_VERIFY_TOKEN
                ),
                "provider": "meta_cloud",
                "active_connectors": whatsapp_connectors.get("active", 0),
                "pending_connectors": whatsapp_connectors.get("pending", 0),
                "inbound_ready": bool(
                    config.META_APP_ID
                    and config.META_APP_SECRET
                    and config.META_WEBHOOK_VERIFY_TOKEN
                    and whatsapp_connectors.get("active", 0)
                ),
                "webhook_url": f"{config.PUBLIC_API_URL.rstrip('/')}/api/v1/ingest/meta/whatsapp" if config.PUBLIC_API_URL else None,
                "legacy_twilio_configured": bool(config.TWILIO_AUTH_TOKEN),
            },
            "telegram": {
                "configured": bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_WEBHOOK_SECRET),
                "operations_chat": bool(config.TELEGRAM_OPERATIONS_CHAT_ID),
                "webhook_url": f"{config.PUBLIC_API_URL.rstrip('/')}/api/v1/ingest/telegram" if config.PUBLIC_API_URL else None,
            },
            "partner_webhook": {
                "configured": bool(config.PARTNER_WEBHOOK_SECRET),
                "webhook_url": f"{config.PUBLIC_API_URL.rstrip('/')}/api/v1/ingest/webhook" if config.PUBLIC_API_URL else None,
            },
        },
        "traffic": {
            "registry": vessel_stats,
        },
        "sar": {
            "open_alerts": sum(1 for a in alerts if a.get("status") != "completed"),
            "completed_alerts": sum(1 for a in alerts if a.get("status") == "completed"),
            "forensic_packets": len(forensic_packets),
        },
        "scheduler": sched,
        "cost_profile": {
            "frontend": "static_vite",
            "backend": "fastapi_polling",
            "state_store": "sqlite_or_postgres",
            "queue": "database_durable" if config.JOB_EXECUTION_MODE == "queue" else "inline_development",
        },
    }


@router.get("/api/v1/ops/stats")
async def ops_stats():
    """
    Heavier stats (DB-backed): alert counts, forensic packets, recent events.
    Polled separately on a longer interval — not needed for initial page load.
    Cached 30s to avoid repeated heavy DB reads.
    """
    global _stats_cache, _stats_cache_ts
    if _stats_cache is not None and (time.monotonic() - _stats_cache_ts) < _STATS_TTL:
        return Response(content=_stats_cache, media_type="application/json")

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

    result = {
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
    payload = json.dumps(result).encode()
    _stats_cache = payload
    _stats_cache_ts = time.monotonic()
    return Response(content=payload, media_type="application/json")


# ── Data injection + compute overview ────────────────────────────────────────

_data_cache: bytes | None = None
_data_cache_ts: float = 0.0
_DATA_TTL = 20.0


def _intel_breakdown() -> dict:
    """What is actually in the intel record, straight from the DB."""
    from datetime import timedelta

    from sqlalchemy import func, select

    from core.db.models import IntelEventDB
    from core.db.session import session_scope

    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()
    with session_scope() as db:
        total = db.execute(select(func.count()).select_from(IntelEventDB)).scalar_one()
        positioned = db.execute(
            select(func.count()).select_from(IntelEventDB).where(IntelEventDB.lat.isnot(None))
        ).scalar_one()
        last_24h = db.execute(
            select(func.count()).select_from(IntelEventDB).where(IntelEventDB.timestamp_utc >= day_ago)
        ).scalar_one()
        last_7d = db.execute(
            select(func.count()).select_from(IntelEventDB).where(IntelEventDB.timestamp_utc >= week_ago)
        ).scalar_one()
        by_type = dict(
            db.execute(
                select(IntelEventDB.type, func.count())
                .where(IntelEventDB.timestamp_utc >= week_ago)
                .group_by(IntelEventDB.type)
            ).all()
        )
        by_source = dict(
            db.execute(
                select(IntelEventDB.source, func.count())
                .where(IntelEventDB.timestamp_utc >= week_ago)
                .group_by(IntelEventDB.source)
            ).all()
        )
        newest = db.execute(select(func.max(IntelEventDB.timestamp_utc))).scalar_one()
    return {
        "total_events": int(total),
        "positioned_events": int(positioned),
        "unpositioned_events": int(total) - int(positioned),
        "events_last_24h": int(last_24h),
        "events_last_7d": int(last_7d),
        "by_type_7d": {k: int(v) for k, v in by_type.items()},
        "by_source_7d": {k: int(v) for k, v in by_source.items()},
        "newest_event_utc": newest,
    }


def _drift_breakdown() -> dict:
    """Drift jobs: how many, in what state, and how long they take."""
    from sqlalchemy import func, select

    from core.db.models import DriftResultDB
    from core.db.session import session_scope

    with session_scope() as db:
        by_status = dict(
            db.execute(select(DriftResultDB.status, func.count()).group_by(DriftResultDB.status)).all()
        )
        recent = db.execute(
            select(DriftResultDB.metadata_json)
            .order_by(DriftResultDB.created_at.desc())
            .limit(20)
        ).scalars().all()
    forcing_mix: dict[str, int] = {}
    model_mix: dict[str, int] = {}
    for meta in recent:
        meta = meta or {}
        q = str(meta.get("forcing_quality") or "unknown")
        forcing_mix[q] = forcing_mix.get(q, 0) + 1
        m = str(meta.get("model") or "unknown")
        model_mix[m] = model_mix.get(m, 0) + 1
    return {
        "by_status": {k: int(v) for k, v in by_status.items()},
        "recent_forcing_quality": forcing_mix,
        "recent_models": model_mix,
    }



# Long-window, database-backed operational history for the Futures Overall view.
# This counts the retained canonical IntelEvent rows, NOT incident findings,
# and never derives fake zero values from failed database calls.
_overall_cache: bytes | None = None
_overall_cache_ts = 0.0
_OVERALL_TTL = 900.0


def _retained_intel_history() -> dict:
    from sqlalchemy import func, select
    from core.db.models import IntelEventDB
    from core.db.session import session_scope

    month = func.substr(IntelEventDB.timestamp_utc, 1, 7)
    with session_scope() as db:
        total, oldest, newest, positioned = db.execute(
            select(
                func.count(IntelEventDB.id),
                func.min(IntelEventDB.timestamp_utc),
                func.max(IntelEventDB.timestamp_utc),
                func.count(IntelEventDB.lat),
            )
        ).one()
        # Ingestion chronology is NOT the source event chronology. A source may
        # describe historical events predating SeaCommons by many years.
        # CAST + SUBSTR works on both SQLite and PostgreSQL.
        from sqlalchemy import String, cast
        ingested_month = func.substr(cast(IntelEventDB.created_at, String), 1, 7)
        first_ingested, last_ingested = db.execute(
            select(func.min(IntelEventDB.created_at), func.max(IntelEventDB.created_at))
        ).one()
        ingested_monthly = db.execute(
            select(ingested_month.label("month"), func.count(IntelEventDB.id))
            .where(IntelEventDB.created_at.is_not(None))
            .group_by(ingested_month)
            .order_by(ingested_month)
        ).all()
        by_type = db.execute(
            select(IntelEventDB.type, func.count(IntelEventDB.id))
            .group_by(IntelEventDB.type)
            .order_by(func.count(IntelEventDB.id).desc())
        ).all()
        monthly = db.execute(
            select(month.label("month"), func.count(IntelEventDB.id))
            .group_by(month)
            .order_by(month)
        ).all()

    return {
        "total_events": int(total),
        "positioned_events": int(positioned),
        "unpositioned_events": int(total) - int(positioned),
        "first_ingested_at": first_ingested.isoformat() if first_ingested else None,
        "last_ingested_at": last_ingested.isoformat() if last_ingested else None,
        "ingested_monthly": [{"month": str(period), "count": int(count)}
                             for period, count in ingested_monthly if period and len(str(period)) == 7],
        "oldest_event_utc": oldest,
        "newest_event_utc": newest,
        "by_type": [{"type": str(category or "unknown"), "count": int(count)}
                    for category, count in by_type],
        "monthly": [{"month": str(period), "count": int(count)}
                    for period, count in monthly if period and len(str(period)) == 7],
    }


@router.get("/api/v1/ops/overall")
async def ops_overall():
    """Retained database-wide OSINT history and monthly trend, cached for 15m.

    No raw evidence payload, identifiers, contact information or precise
    humanitarian geometry are included.
    """
    global _overall_cache, _overall_cache_ts
    if _overall_cache is not None and time.monotonic() - _overall_cache_ts < _OVERALL_TTL:
        return Response(content=_overall_cache, media_type="application/json")
    from fastapi import HTTPException
    try:
        history = await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(None, _retained_intel_history),
            timeout=15.0,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Overall data temporarily unavailable") from exc
    payload = json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "retained_intel_events",
        "count_semantics": "All canonical IntelEvent records currently retained in the database. These are not confirmed incidents.",
        "retention_note": "Overall means all retained historical records; records removed before the retention boundary are not included.",
        "intel_record": history,
    }).encode()
    _overall_cache = payload
    _overall_cache_ts = time.monotonic()
    return Response(content=payload, media_type="application/json")


@router.get("/api/v1/futures/overall")
async def futures_public_overall():
    """Public-safe, cumulative analytics for Futures partner review.

    Only aggregate record counts and month buckets are returned. In particular
    no event types, provenance payload, personal data or case coordinates.
    Reuses the bounded cached canonical query from the internal overall route.
    """
    response = await ops_overall()
    internal = json.loads(response.body)
    record = internal["intel_record"]
    safe = {
        "generated_at": internal["generated_at"],
        "scope": "retained_intel_events",
        "count_semantics": "All retained Intel event records, not verified incidents.",
        "retention_note": "Does not include events erased by past retention policies.",
        "intel_record": {
            "total_events": int(record["total_events"]),
            "positioned_events": int(record["positioned_events"]),
            "first_ingested_at": record.get("first_ingested_at"),
            "last_ingested_at": record.get("last_ingested_at"),
            "ingested_monthly": record.get("ingested_monthly", []),
            "oldest_event_utc": record["oldest_event_utc"],
            "newest_event_utc": record["newest_event_utc"],
            "monthly": record["monthly"],
        },
    }
    return Response(
        content=json.dumps(safe),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=120"},
    )


@router.get("/api/v1/ops/data-status")
async def data_status():
    """One place to see what real data SeaCommons has flowing in and what it
    costs to run: sources, intel volume, vessels, drift load, memory."""
    global _data_cache, _data_cache_ts
    if _data_cache is not None and (time.monotonic() - _data_cache_ts) < _DATA_TTL:
        return Response(content=_data_cache, media_type="application/json")

    from core.drift.opendrift_pool import pool_status

    sources = []
    try:
        from core.intel.source_registry import source_registry

        sources = source_registry.get_all()
    except Exception:
        sources = []

    try:
        client = get_client()
        ngo_client = get_ngo_client()
        ais = {
            "connected": bool(client and client.connected),
            "messages_total": client.messages_received if client else 0,
            "ngo_fleet_connected": bool(ngo_client and ngo_client.connected),
        }
    except Exception:
        ais = {"connected": False, "messages_total": 0}

    try:
        vessels = registry.stats()
    except Exception:
        vessels = {}

    try:
        from core.intel.engine import intel_engine

        monitors = {"monitors_enabled": bool(config.INTEL_MONITORS_ENABLED), **intel_engine.status()}
    except Exception:
        monitors = {"monitors_enabled": bool(config.INTEL_MONITORS_ENABLED)}

    loop = asyncio.get_event_loop()
    try:
        intel, drift = await asyncio.wait_for(
            asyncio.gather(
                loop.run_in_executor(None, _intel_breakdown),
                loop.run_in_executor(None, _drift_breakdown),
            ),
            timeout=8.0,
        )
    except Exception:
        intel, drift = {}, {}

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ingestion": {
            "ais": ais,
            "vessels": vessels,
            "sources": sources,
            "monitors": monitors,
            "image_ocr": _image_ocr_status(),
            "forcing": {
                "cmems_currents": bool(config.CMEMS_USERNAME and config.CMEMS_PASSWORD),
                "open_meteo": "no_key_required",
            },
        },
        "intel_record": intel,
        "drift": {**drift, "engine": pool_status()},
        "compute": {
            "runtime_profile": config.RUNTIME_PROFILE,
            "job_execution_mode": config.JOB_EXECUTION_MODE,
            "available_ram_mb": _available_ram_mb(),
            "database": "sqlite" if config.DATABASE_URL.startswith("sqlite") else "postgres",
        },
    }
    payload = json.dumps(result, default=str).encode()
    _data_cache = payload
    _data_cache_ts = time.monotonic()
    return Response(content=payload, media_type="application/json")


def _available_ram_mb() -> int:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return -1
