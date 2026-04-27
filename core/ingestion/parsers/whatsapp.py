# SPDX-License-Identifier: AGPL-3.0-or-later
"""WhatsApp / Alarm Phone parser."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.ingestion.parsers.base import BaseParser, CoordinateExtractor
from core.ingestion.signal import DistressSignal


class WhatsAppParser(BaseParser):
    """
    Handles all WhatsApp message patterns:
      A — structured Alarm Phone template
      B — Google Maps link in body
      C — unstructured Italian/Arabic/French text
      D — Twilio location share (lat/lon passed as extra params)
    """

    name = "whatsapp"

    def can_parse(self, raw: str) -> bool:
        return True  # fallback parser — accepts anything

    def parse(
        self,
        raw: str,
        source_channel: str,
        source_id: str,
        received_at: datetime,
        extra: dict | None = None,
    ) -> DistressSignal:
        ex = self._extractor
        extra = extra or {}

        # Pattern D — Twilio location share (params come in extra)
        if extra.get("Latitude") and extra.get("Longitude"):
            try:
                lat = float(extra["Latitude"])
                lon = float(extra["Longitude"])
                return DistressSignal(
                    signal_id=str(uuid.uuid4()),
                    source_channel=source_channel,
                    source_id=source_id,
                    raw_text=raw or "[location share]",
                    lat=lat, lon=lon,
                    timestamp_utc=received_at,
                    extraction_confidence=0.98,
                    requires_human_review=False,
                    extraction_method="shared_location",
                    language_detected=ex.detect_language(raw) if raw else None,
                    persons=ex.extract_persons(raw),
                    vessel_type=ex.extract_vessel_type(raw),
                    vessel_condition=ex.extract_vessel_condition(raw),
                    medical_emergency=ex.extract_medical(raw),
                    children_aboard=ex.extract_children(raw),
                )
            except (ValueError, TypeError):
                pass

        # Patterns A / B / C — extract from text
        lat, lon, confidence, method = ex.extract_coords(raw)
        persons    = ex.extract_persons(raw)
        vessel_t   = ex.extract_vessel_type(raw)
        vessel_c   = ex.extract_vessel_condition(raw)
        medical    = ex.extract_medical(raw)
        children   = ex.extract_children(raw)
        lang       = ex.detect_language(raw)

        # Boost confidence if multiple structured fields extracted
        if persons and vessel_t:
            confidence = min(1.0, confidence + 0.05)

        return DistressSignal(
            signal_id=str(uuid.uuid4()),
            source_channel=source_channel,
            source_id=source_id,
            raw_text=raw,
            lat=lat, lon=lon,
            timestamp_utc=received_at,
            persons=persons,
            vessel_type=vessel_t,
            vessel_condition=vessel_c,
            medical_emergency=medical,
            children_aboard=children,
            extraction_confidence=confidence,
            requires_human_review=confidence < 0.70,
            extraction_method=method,
            language_detected=lang,
        )
