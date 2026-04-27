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

# Load .env before anything reads config
_env = Path(__file__).parents[2] / ".env"
if _env.exists():
    load_dotenv(_env)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import config
from core.api.routes import alerts, drift, anomaly, forensic, integrations, ops, vessels
from core.api.routes import ingest, probability, weather
from core.db.session import init_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("seacommons.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Seacommons API starting up (MOCK=%s, DEMO_PUBLIC_MODE=%s)",
        config.MOCK,
        config.DEMO_PUBLIC_MODE,
    )
    init_database()
    _start_background_sensors()
    yield
    logger.info("Seacommons API shutting down")


def _start_background_sensors():
    """Start enabled sensor background threads."""
    if config.DEMO_PUBLIC_MODE:
        logger.info("Public demo mode enabled: skipping background sensor startup")
        return

    try:
        if config.TID_ENABLED or config.MOCK:
            from core.sensors.ionospheric import IonosphericMonitor
            mon = IonosphericMonitor()
            mon.start()
            logger.info("IonosphericMonitor started")
    except Exception as exc:
        logger.warning("IonosphericMonitor failed to start: %s", exc)

    try:
        if config.INFRASOUND_ENABLED or config.MOCK:
            from core.sensors.infrasound import InfrasoundDetector
            InfrasoundDetector().start()
    except Exception as exc:
        logger.warning("InfrasoundDetector failed to start: %s", exc)

    try:
        if config.SEISMIC_ENABLED or config.MOCK:
            from core.sensors.seismic import SeismicDetector
            SeismicDetector().start()
    except Exception as exc:
        logger.warning("SeismicDetector failed to start: %s", exc)

    try:
        if config.ADSB_ENABLED or config.MOCK:
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

    # Start AISStream real-time AIS feed
    if config.AISSTREAM_KEY and not config.MOCK:
        try:
            from core.vessels import aisstream
            aisstream.start(config.AISSTREAM_KEY)
            logger.info("AISStream client started with key %s...", config.AISSTREAM_KEY[:8])
        except Exception as exc:
            logger.warning("AISStream failed to start: %s", exc)


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


@app.get("/health")
async def health():
    return {"status": "ok", "mock": config.MOCK, "demo_public_mode": config.DEMO_PUBLIC_MODE}


@app.get("/api/v1/config")
async def get_config():
    return {
        "mock": config.MOCK,
        "demo_public_mode": config.DEMO_PUBLIC_MODE,
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
