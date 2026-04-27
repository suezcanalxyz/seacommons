# SPDX-License-Identifier: AGPL-3.0-or-later
"""Twitter / X monitoring parser — passive ingestion only."""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from core.ingestion.parsers.base import BaseParser, CoordinateExtractor
from core.ingestion.signal import DistressSignal

TRUSTED_ACCOUNTS = {
    "alarm_phone", "seawatch_intl", "msf_sea",
    "sosmediterranee", "sos_humanity", "watchthemed",
}
TRUSTED_HASHTAGS = {
    "medrescue", "watchthemed", "mediterranean",
    "boatpeople", "refugeesatsea",
}
_RE_HASHTAG = re.compile(r'#(\w+)')
_RE_HANDLE  = re.compile(r'@(\w+)')
_MAX_CONF   = 0.80


class TwitterParser(BaseParser):
    """
    Parses Twitter/X status objects (plain text or dict updates).

    Rules:
    - Passive monitoring only — no outbound replies ever.
    - Max extraction_confidence is capped at 0.80.
    - Retweets are skipped unless the original author is a trusted account.
    - Boost +0.10 if author is trusted; +0.05 per trusted hashtag (max +0.15).
    """

    name = "twitter"

    def can_parse(self, raw: str) -> bool:
        return True

    def parse(
        self,
        raw: str,
        source_channel: str,
        source_id: str,
        received_at: datetime,
        tweet: dict | None = None,
    ) -> DistressSignal:
        ex = self._extractor
        tweet = tweet or {}

        # Resolve author handle
        user = tweet.get("user") or tweet.get("author") or {}
        author_handle = (user.get("screen_name") or user.get("username") or "").lower()

        # Skip retweet unless original author is trusted
        is_rt = raw.startswith("RT @") or bool(tweet.get("retweeted_status"))
        if is_rt:
            rt_match = re.match(r'RT @(\w+)', raw)
            rt_author = rt_match.group(1).lower() if rt_match else ""
            if rt_author not in TRUSTED_ACCOUNTS and author_handle not in TRUSTED_ACCOUNTS:
                # Still parse but with very low confidence
                return DistressSignal(
                    signal_id=str(uuid.uuid4()),
                    source_channel=source_channel,
                    source_id=source_id,
                    raw_text=raw,
                    lat=None, lon=None,
                    timestamp_utc=received_at,
                    extraction_confidence=0.0,
                    requires_human_review=True,
                    extraction_method="none",
                    language_detected=ex.detect_language(raw),
                )

        # Base extraction
        lat, lon, confidence, method = ex.extract_coords(raw)

        # Trust boosts
        boost = 0.0
        if author_handle in TRUSTED_ACCOUNTS:
            boost += 0.10

        hashtags = {h.lower() for h in _RE_HASHTAG.findall(raw)}
        trusted_ht_count = len(hashtags & TRUSTED_HASHTAGS)
        boost += min(0.15, trusted_ht_count * 0.05)

        confidence = min(_MAX_CONF, confidence + boost)

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
