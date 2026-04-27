# SPDX-License-Identifier: AGPL-3.0-or-later
"""Telegram Bot API message parser."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.ingestion.parsers.base import BaseParser, CoordinateExtractor
from core.ingestion.signal import DistressSignal

_TRUSTED_CHANNELS = {"alarm_phone", "watchthemed", "seawatch_intl"}


class TelegramParser(BaseParser):
    """
    Parses Telegram Bot API update objects (dicts) and plain text.
    Handles location shares, forwarded messages from trusted channels,
    and unstructured text in multiple languages.
    """

    name = "telegram"

    def can_parse(self, raw: str) -> bool:
        return True

    def parse(
        self,
        raw: str,
        source_channel: str,
        source_id: str,
        received_at: datetime,
        update: dict | None = None,
    ) -> DistressSignal:
        ex = self._extractor
        update = update or {}
        confidence_boost = 0.0

        lat: float | None = None
        lon: float | None = None
        method = "regex"

        # 1. Telegram location share
        msg = update.get("message", {})
        location = msg.get("location")
        if location:
            lat = float(location["latitude"])
            lon = float(location["longitude"])
            method = "shared_location"
            raw = raw or "[telegram location share]"
            lat_f, lon_f, confidence, _ = lat, lon, 0.98, method
        else:
            lat_f, lon_f, confidence, method = ex.extract_coords(raw)

        # 2. Forwarded from trusted channels → boost confidence
        fwd = msg.get("forward_from_chat", {})
        fwd_name = (fwd.get("username") or fwd.get("title") or "").lower()
        if any(t in fwd_name for t in _TRUSTED_CHANNELS):
            confidence_boost = 0.05

        confidence = min(1.0, confidence + confidence_boost)

        return DistressSignal(
            signal_id=str(uuid.uuid4()),
            source_channel=source_channel,
            source_id=source_id,
            raw_text=raw,
            lat=lat_f, lon=lon_f,
            timestamp_utc=received_at,
            persons=ex.extract_persons(raw),
            vessel_type=ex.extract_vessel_type(raw),
            vessel_condition=ex.extract_vessel_condition(raw),
            medical_emergency=ex.extract_medical(raw),
            children_aboard=ex.extract_children(raw),
            extraction_confidence=confidence,
            requires_human_review=confidence < 0.70,
            extraction_method=method,
            language_detected=ex.detect_language(raw),
        )
