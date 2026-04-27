# SPDX-License-Identifier: AGPL-3.0-or-later
"""SMS / Iridium parser."""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from core.ingestion.parsers.base import BaseParser, CoordinateExtractor
from core.ingestion.signal import DistressSignal

# Iridium format: POSITION:35.123N/15.456E PERS:45 TYPE:RB
_RE_IRIDIUM = re.compile(
    r'POSITION\s*:\s*(-?\d+\.?\d*)[NS]?/(-?\d+\.?\d*)[EW]?\s+'
    r'(?:PERS\s*:\s*(\d+))?\s*(?:TYPE\s*:\s*(\w+))?',
    re.IGNORECASE,
)
_IRIDIUM_TYPES = {'RB': 'rubber_boat', 'WB': 'wooden_boat', 'SB': 'sailboat'}
_RE_TRANSCRIPT = re.compile(r'^\[TRANSCRIPT\]', re.IGNORECASE)


class SMSParser(BaseParser):
    """
    Parses SMS messages including:
    - Iridium satellite position reports
    - Standard GSM text
    - Voicemail transcripts (prefixed [TRANSCRIPT])
    """

    name = "sms"

    def can_parse(self, raw: str) -> bool:
        return True

    def parse(
        self,
        raw: str,
        source_channel: str,
        source_id: str,
        received_at: datetime,
    ) -> DistressSignal:
        ex = self._extractor

        # 1. Iridium format
        m = _RE_IRIDIUM.search(raw)
        if m:
            lat = float(m.group(1))
            lon = float(m.group(2))
            persons = int(m.group(3)) if m.group(3) else None
            vtype = _IRIDIUM_TYPES.get((m.group(4) or '').upper())
            return DistressSignal(
                signal_id=str(uuid.uuid4()),
                source_channel=source_channel,
                source_id=source_id,
                raw_text=raw,
                lat=lat, lon=lon,
                timestamp_utc=received_at,
                persons=persons,
                vessel_type=vtype,
                vessel_condition=ex.extract_vessel_condition(raw),
                medical_emergency=ex.extract_medical(raw),
                children_aboard=ex.extract_children(raw),
                extraction_confidence=0.97,
                requires_human_review=False,
                extraction_method="iridium",
                language_detected=None,
            )

        # 2. Voicemail transcript — lower confidence baseline
        is_transcript = bool(_RE_TRANSCRIPT.match(raw))
        base_conf_boost = -0.10 if is_transcript else 0.0

        lat, lon, confidence, method = ex.extract_coords(raw)
        confidence = max(0.0, confidence + base_conf_boost)

        return DistressSignal(
            signal_id=str(uuid.uuid4()),
            source_channel=source_channel,
            source_id=source_id,
            raw_text=raw,
            lat=lat, lon=lon,
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
