# SPDX-License-Identifier: AGPL-3.0-or-later
"""Telegram Bot API channel handler."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.ingestion.parsers.telegram import TelegramParser
from core.ingestion.signal import DistressSignal

_parser = TelegramParser()


def handle_telegram_update(update: dict[str, Any]) -> DistressSignal | None:
    """
    Process a Telegram Bot API Update object.

    Returns None if the update contains no parsable message.
    Only handles 'message' updates (not inline queries, callbacks, etc.).
    """
    msg = update.get("message")
    if not msg:
        return None

    # Extract text — prefer caption for media messages
    raw = msg.get("text") or msg.get("caption") or ""

    # If it's a location-only message, raw will be empty
    if not raw and not msg.get("location"):
        return None

    source_id = str(
        msg.get("from", {}).get("username")
        or msg.get("from", {}).get("id")
        or msg.get("chat", {}).get("id")
        or "unknown"
    )

    # Prefer message date from Telegram (Unix timestamp)
    ts = msg.get("date")
    received_at = (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        if ts else datetime.now(timezone.utc)
    )

    return _parser.parse(
        raw=raw,
        source_channel="telegram",
        source_id=source_id,
        received_at=received_at,
        update=update,
    )
