# SPDX-License-Identifier: AGPL-3.0-or-later
"""Standalone intel-monitors process — no FastAPI, no HTTP server.

Runs the same background sensors, intel monitors and scheduler as the API
process (core.api.main), against the same shared database, so it can run on
a separate VM from the API. Auto-drift triggers go over HTTP to the API's
own /api/v1/intel/auto-drift (see core/intel/auto_drift_client.py) rather
than an in-process call, since this is a different process entirely.

Run with: python3 -m core.intel_worker_main
"""
from __future__ import annotations

import logging
import signal
import time

from core.config import config
from core import bootstrap
from core.db.session import init_database
from core.observability import configure_logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
configure_logging()
logger = logging.getLogger("seacommons.intel_worker")

_running = True


def _handle_stop(signum, frame):
    global _running
    logger.info("Intel worker received signal %s, shutting down", signum)
    _running = False


def main() -> None:
    logger.info("Intel worker starting up (RUNTIME_PROFILE=%s)", config.RUNTIME_PROFILE)
    init_database()
    bootstrap.reset_stale_computing_jobs()
    try:
        from core.intel.store import intel_store
        intel_store.load_from_db()
        intel_store.reset_computing_drifts()
    except Exception as exc:
        logger.warning("Intel DB reload failed: %s", exc)

    bootstrap.start_background_sensors()
    bootstrap.start_intel_engine()
    bootstrap.start_scheduler()

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    logger.info("Intel worker running (monitors + scheduler active)")
    while _running:
        time.sleep(1)

    try:
        from core.scheduler import stop as scheduler_stop
        scheduler_stop()
    except Exception:
        pass
    logger.info("Intel worker stopped")


if __name__ == "__main__":
    main()
