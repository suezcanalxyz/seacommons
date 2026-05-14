# SPDX-License-Identifier: AGPL-3.0-or-later
"""SuezCanal core API entry point."""
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional during bootstrap
    def load_dotenv(*_args, **_kwargs):
        return False

# Load .env — prefer repo root first so local/dev/prod use one canonical runtime profile
for _env in [
    Path(__file__).parents[4] / ".env",   # repo root       (local dev)
    Path(__file__).parents[2] / ".env",   # apps/api/.env   (legacy fallback)
]:
    if _env.exists():
        load_dotenv(_env)
        break

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import config
from core.api.routes import alerts, drift, anomaly, forensic, integrations, ops, vessels
from core.api.routes import ingest, probability, weather, zones, intel
from core.db.session import init_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("seacommons.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Seacommons API starting up (RUNTIME_PROFILE=%s)",
        config.RUNTIME_PROFILE,
    )
    init_database()
    _reset_stale_computing_jobs()
    try:
        from core.intel.store import intel_store
        intel_store.load_from_db()
        intel_store.reset_computing_drifts()
    except Exception as exc:
        logger.warning("Intel DB reload failed: %s", exc)
    try:
        from core.drift.opendrift_pool import prewarm
        prewarm()
    except Exception as exc:
        logger.warning("OpenDrift prewarm failed to start: %s", exc)
    _start_background_sensors()
    _start_intel_engine()
    _start_scheduler()
    yield
    logger.info("Seacommons API shutting down")
    try:
        from core.scheduler import stop as scheduler_stop
        scheduler_stop()
    except Exception:
        pass


def _reset_stale_computing_jobs() -> None:
    """
    At startup, mark any drift/alert jobs stuck in 'computing' as 'failed'.
    They were killed by the previous process shutdown and will never complete.
    Also resets drift_status on in-memory intel events so the UI shows a retry button.
    """
    try:
        from core.db.session import session_scope
        from core.db.models import DriftResultDB, AlertEvent
        from sqlalchemy import update
        with session_scope() as db:
            result = db.execute(
                update(DriftResultDB)
                .where(DriftResultDB.status == "computing")
                .values(status="failed")
            )
            n_drift = result.rowcount
        with session_scope() as db:
            result = db.execute(
                update(AlertEvent)
                .where(AlertEvent.status == "processing")
                .values(status="failed")
            )
            n_alert = result.rowcount
        if n_drift or n_alert:
            logger.info("Startup cleanup: reset %d stuck drift jobs, %d stuck alerts to 'failed'", n_drift, n_alert)
    except Exception as exc:
        logger.warning("Startup cleanup failed: %s", exc)


def _start_background_sensors():
    """Start enabled sensor background threads."""
    try:
        if config.TID_ENABLED:
            from core.sensors.ionospheric import IonosphericMonitor
            mon = IonosphericMonitor()
            mon.start()
            logger.info("IonosphericMonitor started")
    except Exception as exc:
        logger.warning("IonosphericMonitor failed to start: %s", exc)

    try:
        if config.INFRASOUND_ENABLED:
            from core.sensors.infrasound import InfrasoundDetector
            InfrasoundDetector().start()
    except Exception as exc:
        logger.warning("InfrasoundDetector failed to start: %s", exc)

    try:
        if config.SEISMIC_ENABLED:
            from core.sensors.seismic import SeismicDetector
            SeismicDetector().start()
    except Exception as exc:
        logger.warning("SeismicDetector failed to start: %s", exc)

    try:
        if config.ADSB_ENABLED:
            from core.sensors.adsb import ADSBReceiver
            ADSBReceiver().start()
    except Exception as exc:
        logger.warning("ADSBReceiver failed to start: %s", exc)

    # Start correlation engine
    try:
        from core.anomaly.correlation import CorrelationEngine
        engine = CorrelationEngine()
        import threading
        t = threading.Thread(target=engine.start, daemon=True)
        t.start()
    except Exception as exc:
        logger.warning("CorrelationEngine failed to start: %s", exc)

    # Start AISStream real-time AIS feed (BarentsWatch already started above)
    if config.AISSTREAM_KEY:
        try:
            from core.vessels import aisstream
            aisstream.start(config.AISSTREAM_KEY)
            logger.info("AISStream client started")
        except Exception as exc:
            logger.warning("AISStream failed to start: %s", exc)
    else:
        logger.warning("AISStream key missing: live vessel feed disabled")


def _start_scheduler() -> None:
    """Start APScheduler: drift-pending, news refresh, IOM incidents, forensic scan."""
    try:
        from core.scheduler import start as scheduler_start
        scheduler_start()
    except Exception as exc:
        logger.warning("Scheduler failed to start: %s", exc)


def _start_intel_engine() -> None:
    """Start maritime intelligence monitors (Twitter, news, AIS spikes)."""
    if not config.INTEL_ENABLED:
        logger.info("Intel engine disabled (INTEL_ENABLED=false)")
        return
    try:
        from core.intel.engine import intel_engine
        intel_engine.start(
            twitter_bearer=config.TWITTER_BEARER_TOKEN,
            twscrape_accounts=config.TWITTER_ACCOUNTS,
        )
        logger.info("Intel engine started")
    except Exception as exc:
        logger.warning("Intel engine failed to start: %s", exc)


app = FastAPI(
    title="Seacommons",
    description="Operational maritime SAR and signal dashboard",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts.router)
app.include_router(drift.router)
app.include_router(anomaly.router)
app.include_router(forensic.router)
app.include_router(integrations.router)
app.include_router(ops.router)
app.include_router(vessels.router)
app.include_router(ingest.router)
app.include_router(probability.router)
app.include_router(weather.router)
app.include_router(zones.router)
app.include_router(intel.router)


@app.get("/health")
async def health():
    return {"status": "ok", "runtime_profile": config.RUNTIME_PROFILE}


@app.get("/api/v1/config")
async def get_config():
    return {
        "runtime_profile": config.RUNTIME_PROFILE,
        "sensors": {
            "infrasound": config.INFRASOUND_ENABLED,
            "seismic": config.SEISMIC_ENABLED,
            "tid": config.TID_ENABLED,
            "gnss": config.GNSS_ENABLED,
            "adsb": config.ADSB_ENABLED,
            "sdr": config.SDR_ENABLED,
        },
        "aisstream": bool(config.AISSTREAM_KEY),
    }
