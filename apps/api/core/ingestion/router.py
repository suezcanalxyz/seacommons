# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Ingestion router — receives raw messages from all channels,
dispatches to the correct parser, stores DistressSignals.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Callable, Any

from core.ingestion.channels.twilio import handle_twilio_whatsapp, handle_twilio_sms
from core.ingestion.channels.telegram_bot import handle_telegram_update
from core.ingestion.channels.webhook import handle_webhook
from core.ingestion.signal import DistressSignal

logger = logging.getLogger(__name__)

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
    """Return the most recent signals from the canonical database."""
    from sqlalchemy import select
    from core.db.models import IngestedSignalDB
    from core.db.session import session_scope
    with session_scope() as db:
        rows = db.execute(select(IngestedSignalDB).order_by(IngestedSignalDB.received_at.desc()).limit(limit)).scalars()
        return [DistressSignal.model_validate(row.payload) for row in rows]


# ── Internal ──────────────────────────────────────────────────────────────────

def _save_and_notify(sig: DistressSignal) -> None:
    if sig.provider_message_id:
        sig.signal_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"seacommons:{sig.source_channel}:{sig.provider_message_id}"))
    if not _persist(sig):
        logger.info("duplicate inbound delivery ignored: %s", sig.signal_id)
        return
    with _lock:
        subs = list(_subscribers)
    for fn in subs:
        try:
            fn(sig)
        except Exception as exc:
            logger.warning("subscriber error: %s", exc)


def _persist(sig: DistressSignal) -> bool:
    from sqlalchemy.exc import IntegrityError
    from core.db.models import IngestedSignalDB
    from core.db.session import session_scope
    try:
        with session_scope() as db:
            db.add(IngestedSignalDB(
                signal_id=sig.signal_id,
                source_channel=sig.source_channel,
                source_id=sig.source_id,
                provider_message_id=sig.provider_message_id,
                payload=sig.model_dump(mode="json"),
            ))
        return True
    except IntegrityError:
        return False
    except Exception as exc:
        logger.error("failed to persist signal %s: %s", sig.signal_id, exc)
        raise
