# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared startup routines for background sensors, intel monitors and the
scheduler — used by both the API process (core.api.main) and the standalone
intel-worker process (core.intel_worker_main) so a split deployment (API on
one VM, monitors on another) runs the exact same startup code as the
co-located single-process deployment.
"""
from __future__ import annotations

import logging

from core.config import config

logger = logging.getLogger("seacommons.bootstrap")


def reset_stale_computing_jobs() -> None:
    """At startup, mark any drift/alert jobs stuck in 'computing' as 'failed'.

    They were killed by the previous process shutdown and will never complete.
    """
    try:
        from sqlalchemy import update

        from core.db.models import AlertEvent, DriftResultDB
        from core.db.session import session_scope
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


def start_background_sensors() -> None:
    """Start enabled sensor background threads (AIS feeds, correlation engine, etc)."""
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

    try:
        from core.anomaly.correlation import CorrelationEngine
        # No Redis is deployed (and nothing else in this codebase publishes to
        # the sensor pubsub channels it would subscribe to), so the Redis
        # loop just spun on "connection refused" forever. in_memory=True runs
        # its queue-based loop instead — functionally equivalent here since
        # there's no external publisher either way, minus the log noise.
        engine = CorrelationEngine(in_memory=True)
        import threading
        t = threading.Thread(target=engine.start, daemon=True)
        t.start()
    except Exception as exc:
        logger.warning("CorrelationEngine failed to start: %s", exc)

    if config.AISSTREAM_KEY:
        try:
            from core.vessels import aisstream
            aisstream.start(config.AISSTREAM_KEY, ngo_api_key=config.AISSTREAM_NGO_KEY)
            logger.info("AISStream client started")
        except Exception as exc:
            logger.warning("AISStream failed to start: %s", exc)
    else:
        logger.warning("AISStream key missing: live vessel feed disabled")


def start_scheduler() -> None:
    """Start APScheduler: news refresh, source health, IOM incidents, forensic scan."""
    try:
        from core.scheduler import start as scheduler_start
        scheduler_start()
    except Exception as exc:
        logger.warning("Scheduler failed to start: %s", exc)


def start_intel_engine() -> None:
    """Start maritime intelligence monitors (twikit, GDACS, AIS spikes, ...)."""
    if not config.INTEL_ENABLED:
        logger.info("Intel engine disabled (INTEL_ENABLED=false)")
        return
    try:
        from core.intel.engine import intel_engine
        intel_engine.start(
            twitter_bearer=config.TWITTER_BEARER_TOKEN,
            twikit_enabled=config.TWIKIT_ENABLED,
            twikit_cookies_file=config.TWIKIT_COOKIES_FILE,
            twikit_accounts=config.TWIKIT_ACCOUNTS,
            twikit_poll_interval_s=config.TWIKIT_POLL_INTERVAL_S,
            twikit_priority_accounts=config.TWIKIT_PRIORITY_ACCOUNTS,
            twikit_priority_poll_interval_s=config.TWIKIT_PRIORITY_POLL_INTERVAL_S,
            twikit_alerts_enabled=config.TWIKIT_ALERTS_ENABLED,
        )
        logger.info("Intel engine started")
    except Exception as exc:
        logger.warning("Intel engine failed to start: %s", exc)
