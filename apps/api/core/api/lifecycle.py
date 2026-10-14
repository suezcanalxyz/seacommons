# SPDX-License-Identifier: AGPL-3.0-or-later
"""Orderly API background shutdown. Never signal or restart systemd."""
from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger("seacommons.lifecycle")


def stop_background_services() -> list[str]:
    """Stop background producers before consumers, isolating each failure.

    This prevents decoder children and socket reader threads from surviving
    FastAPI's lifespan. Every stop is idempotent; exceptions must not skip the
    remaining cleanups. No database rows or decoded evidence are deleted.
    """
    from core.scheduler import stop as scheduler_stop
    from core.intel.engine import intel_engine
    from core.vessels.aisstream import stop_clients as stop_ais_clients
    from core.radio.runtime import stop_remote_radio
    from core.radio.decoder_runtime import stop_radio_decoder_runtime
    from core.intel.media_ocr_queue import media_ocr_queue

    operations: tuple[tuple[str, Callable[[], None]], ...] = (
        ("scheduler", scheduler_stop),
        ("intel_monitors", intel_engine.stop),
        ("ais_subscriptions", stop_ais_clients),
        ("radio_receivers", stop_remote_radio),
        ("radio_decoders", stop_radio_decoder_runtime),
        ("media_ocr_queue", media_ocr_queue.shutdown),
    )
    failed = []
    for name, stop in operations:
        try:
            stop()
        except Exception:
            failed.append(name)
            logger.exception("Background service shutdown failed: %s", name)
    return failed
