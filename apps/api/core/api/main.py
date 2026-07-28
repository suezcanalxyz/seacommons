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
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi import HTTPException

from core.config import config
from core.api.routes import alerts, drift, anomaly, forensic, integrations, ops, vessels
from core.api.routes import ingest, probability, weather, zones, intel, cases, governance, live
from core.db.session import init_database
from core.security import READ_ROLES, WRITE_ROLES, require_roles, validate_production_security
from core.observability import configure_logging, metrics_middleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
configure_logging()
logger = logging.getLogger("seacommons.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_production_security()
    logger.info(
        "Seacommons API starting up (RUNTIME_PROFILE=%s)",
        config.RUNTIME_PROFILE,
    )
    init_database()
    if config.JOB_EXECUTION_MODE != "queue":
        _reset_stale_computing_jobs()
    try:
        from core.intel.store import intel_store
        intel_store.load_from_db()
        intel_store.reset_computing_drifts()
    except Exception as exc:
        logger.warning("Intel DB reload failed: %s", exc)
    if config.JOB_EXECUTION_MODE != "queue" and not config.DEMO_PUBLIC_MODE:
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
        intel_engine.start(twitter_bearer=config.TWITTER_BEARER_TOKEN)
        logger.info("Intel engine started")
    except Exception as exc:
        logger.warning("Intel engine failed to start: %s", exc)


app = FastAPI(
    title="Seacommons",
    description="Operational maritime SAR and signal dashboard",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.middleware("http")(metrics_middleware)


@app.middleware("http")
async def authorization_gate(request, call_next):
    """Protect operational reads and all mutations; webhook authenticity is route-specific."""
    path = request.url.path
    if config.DEMO_PUBLIC_MODE and request.method not in {"GET", "HEAD", "OPTIONS"} and not (
        request.method == "POST" and path == "/api/v1/alert"
    ):
        return JSONResponse(status_code=403, content={"detail": "This operation is disabled in the public demo"})
    public = path in {
        "/health", "/ready", "/metrics", "/docs", "/openapi.json", "/redoc",
        "/api/v1/ingest/twilio/whatsapp", "/api/v1/ingest/twilio/sms",
        "/api/v1/ingest/telegram", "/api/v1/ingest/webhook",
    } or (
        request.method in {"GET", "HEAD", "OPTIONS"}
        and path.startswith("/api/v1/live/")
    )
    try:
        if not public:
            if path.startswith(("/api/v1/admin", "/api/v1/governance")):
                require_roles(request, {"administrator"})
            elif request.method not in {"GET", "HEAD", "OPTIONS"}:
                require_roles(request, WRITE_ROLES)
            elif path.startswith(("/api/v1/forensic", "/api/v1/intel", "/api/v1/ingest/signals", "/api/v1/inbox", "/api/v1/cases", "/api/v1/audit", "/api/v1/jobs", "/api/v1/admin")):
                require_roles(request, READ_ROLES)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)

# CORS: allow_credentials MUST be False when allow_origins=["*"].
# Starlette ≥0.40 raises ValueError otherwise (HTTP spec violation).
# The frontend never sends cookies, so credentials=False is correct.
# Production frontends use the dedicated SeaCommons API hosts. Local origins
# remain available for development.
_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS",
    "https://console.seacommons.org,https://demo.seacommons.org,"
    "http://localhost:5173,http://localhost:3000,http://localhost:8000",
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
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
app.include_router(cases.router)
app.include_router(governance.router)
app.include_router(live.router)


@app.get("/health")
async def health():
    return {"status": "ok", "runtime_profile": config.RUNTIME_PROFILE}


@app.get("/ready")
async def ready():
    from core.db.session import engine
    from sqlalchemy import text
    try:
        with engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "error"})


@app.get("/metrics")
async def metrics():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from core.observability import refresh_operational_gauges
    refresh_operational_gauges()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
