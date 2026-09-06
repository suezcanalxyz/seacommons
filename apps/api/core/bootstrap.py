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
        from core.intel import fusion as _fusion

        # No Redis is deployed (and nothing else in this codebase publishes to
        # the sensor pubsub channels it would subscribe to), so the Redis
        # loop just spun on "connection refused" forever. in_memory=True runs
        # its queue-based loop instead — functionally equivalent here since
        # there's no external publisher either way, minus the log noise.
        engine = CorrelationEngine(in_memory=True, on_threat=_fusion.emit_physical_threat)
        import threading
        t = threading.Thread(target=engine.start, daemon=True)
        t.start()
        # Register the OSINT fusion engine on the intel store and let it feed
        # AIS anomalies into the sensor-fusion engine (vessel_spoofing_confirmed).
        _fusion.set_correlation_engine(engine)
        _fusion.register()
    except Exception as exc:
        logger.warning("Correlation/fusion engine failed to start: %s", exc)

    try:
        from core.intel import humanitarian_incident

        humanitarian_incident.register()
    except Exception as exc:
        logger.warning("Humanitarian incident sync failed to start: %s", exc)

    _start_ais_feeds()
    _start_remote_radio()



def _start_remote_radio() -> None:
    """Register radio as one acquisition adapter and start it when enabled."""
    try:
        from core.radio.bridge import register_radio_acquisition_status

        register_radio_acquisition_status()
    except Exception as exc:
        logger.warning("Radio acquisition status registration failed: %s", type(exc).__name__)
    if not config.REMOTE_RADIO_ENABLED:
        return
    try:
        from core.radio.runtime import start_remote_radio_from_config

        runtime = start_remote_radio_from_config()
        logger.info("Remote radio runtime started: %s", runtime.status())
    except Exception as exc:
        logger.warning("Remote radio runtime failed to start: %s", type(exc).__name__)



def _start_ais_feeds() -> None:
    """Start AIS providers through the staged fusion runtime.

    `legacy` is intentionally identical to the historical AISStream-only
    startup path. `shadow` adds aiscast without changing canonical writes;
    `fused` is the only mode allowed to cut canonical positions over.
    """
    if not config.AISSTREAM_KEY:
        logger.warning("AISStream key missing: live vessel feed disabled")
        return
    try:
        from core.vessels.ais_runtime import start_sources
        runtime = start_sources(
            mode=config.AIS_FUSION_MODE,
            aisstream_key=config.AISSTREAM_KEY,
            ngo_api_key=config.AISSTREAM_NGO_KEY,
            aiscast_enabled=config.AISCAST_ENABLED,
            aiscast_bbox=config.AISCAST_BBOX,
            aiscast_mmsi_limit=config.AISCAST_NGO_MMSI_LIMIT,
            aiscast_url=config.AISCAST_WS_URL,
        )
        logger.info("AIS runtime started (mode=%s, aiscast=%s)",
                    runtime.mode, runtime.status().get("aiscast_started"))
    except Exception as exc:
        logger.warning("AIS runtime failed to start: %s", exc)


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
