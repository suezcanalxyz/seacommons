# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Ingestion router — receives raw messages from all channels,
dispatches to the correct parser, stores DistressSignals.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any

from core.ingestion.channels.twilio import handle_twilio_whatsapp, handle_twilio_sms
from core.ingestion.channels.telegram_bot import handle_telegram_update
from core.ingestion.channels.webhook import handle_webhook
from core.ingestion.signal import DistressSignal

logger = logging.getLogger(__name__)

_STORE_PATH = Path(__file__).parent.parent / "data" / "distress_signals.jsonl"
_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)

_subscribers: list[Callable[[DistressSignal], None]] = []
_lock = threading.Lock()


# ── Public API ────────────────────────────────────────────────────────────────

def subscribe(fn: Callable[[DistressSignal], None]) -> None:
    """Register a callback invoked whenever a new DistressSignal is ingested."""
    with _lock:
        _subscribers.append(fn)


def ingest_twilio_whatsapp(form: dict[str, Any]) -> DistressSignal:
    sig = handle_twilio_whatsapp(form)
    _save_and_notify(sig)
    return sig


def ingest_twilio_sms(form: dict[str, Any]) -> DistressSignal:
    sig = handle_twilio_sms(form)
    _save_and_notify(sig)
    return sig


def ingest_telegram(update: dict[str, Any]) -> DistressSignal | None:
    sig = handle_telegram_update(update)
    if sig:
        _save_and_notify(sig)
    return sig


def ingest_webhook(payload: dict[str, Any]) -> DistressSignal:
    sig = handle_webhook(payload)
    _save_and_notify(sig)
    return sig


def load_recent(limit: int = 200) -> list[DistressSignal]:
    """Return the most recent signals from the JSONL store."""
    if not _STORE_PATH.exists():
        return []
    lines = _STORE_PATH.read_text(encoding="utf-8").splitlines()
    signals = []
    for line in lines[-limit:]:
        line = line.strip()
        if line:
            try:
                signals.append(DistressSignal.from_dict(json.loads(line)))
            except Exception:
                pass
    return list(reversed(signals))


# ── Internal ──────────────────────────────────────────────────────────────────

def _save_and_notify(sig: DistressSignal) -> None:
    _persist(sig)
    with _lock:
        subs = list(_subscribers)
    for fn in subs:
        try:
            fn(sig)
        except Exception as exc:
            logger.warning("subscriber error: %s", exc)


def _persist(sig: DistressSignal) -> None:
    try:
        with _lock:
            with _STORE_PATH.open("a", encoding="utf-8") as f:
                f.write(sig.model_dump_json() + "\n")
    except Exception as exc:
        logger.error("failed to persist signal %s: %s", sig.signal_id, exc)
