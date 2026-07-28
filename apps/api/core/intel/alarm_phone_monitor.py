# SPDX-License-Identifier: AGPL-3.0-or-later
"""Collect Alarm Phone's public X timeline from its first-party website.

Alarm Phone republishes its X posts in the server-rendered HTML at
alarmphone.org. This narrow collector reads that official public copy without
an X login, account automation, or an unofficial social-media mirror.
"""
from __future__ import annotations

import html
import logging
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from core.intel.geoextract import classify_severity, extract_coords, is_distress
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

SOURCE_NAME = "Alarm Phone / X official site"
PAGE_URL = "https://alarmphone.org/en/"
_POLL_INTERVAL_S = 90
_X_EPOCH_MS = 1_288_834_974_657
_HEADERS = {
    "User-Agent": "SeaCommonsIntel/2.0 (+https://seacommons.org)",
    "Accept": "text/html,application/xhtml+xml",
}
_ITEM_RE = re.compile(
    r'<div[^>]*class="[^"]*\bctf-item\b[^"]*"[^>]*\bid="(?P<id>\d+)"[^>]*>'
    r"(?P<body>.*?)(?=<div[^>]*class=\"[^\"]*\bctf-item\b|\Z)",
    re.I | re.S,
)
_TEXT_RE = re.compile(
    r'<p[^>]*class="[^"]*\bctf-tweet-text\b[^"]*"[^>]*>(?P<text>.*?)</p>',
    re.I | re.S,
)
_TAG_RE = re.compile(r"<[^>]+>")


def x_id_timestamp(tweet_id: str) -> str:
    """Recover the exact UTC creation time encoded in an X Snowflake ID."""
    milliseconds = (int(tweet_id) >> 22) + _X_EPOCH_MS
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).isoformat()


def parse_official_timeline(document: str) -> list[dict[str, str]]:
    """Extract post IDs and text from Alarm Phone's server-rendered timeline."""
    posts: list[dict[str, str]] = []
    for item in _ITEM_RE.finditer(document):
        text_match = _TEXT_RE.search(item.group("body"))
        if not text_match:
            continue
        raw_text = re.sub(r"<br\s*/?>", "\n", text_match.group("text"), flags=re.I)
        text = html.unescape(_TAG_RE.sub(" ", raw_text))
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        tweet_id = item.group("id")
        posts.append(
            {
                "id": tweet_id,
                "text": text,
                "created_at": x_id_timestamp(tweet_id),
                "url": f"https://x.com/alarm_phone/status/{tweet_id}",
            }
        )
    return posts


class AlarmPhoneMonitor:
    """Continuously collect public Alarm Phone posts from alarmphone.org."""

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        from core.intel.source_registry import source_registry

        source_registry.register(SOURCE_NAME, "twitter")
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="intel-alarm-phone-official",
        )
        self._thread.start()
        logger.info("Alarm Phone first-party X timeline monitor started")

    def stop(self) -> None:
        self._running = False

    def scan(self) -> None:
        """Run one immediate collection cycle."""
        from core.intel.source_registry import source_registry

        new_count = 0
        error: Optional[str] = None
        try:
            request = urllib.request.Request(PAGE_URL, headers=_HEADERS)
            with urllib.request.urlopen(request, timeout=20) as response:
                document = response.read().decode("utf-8", errors="replace")
            for post in parse_official_timeline(document):
                if self._ingest(post):
                    new_count += 1
        except Exception as exc:
            error = str(exc)
            logger.warning("Alarm Phone official timeline error: %s", exc)
        source_registry.record_poll(SOURCE_NAME, events_found=new_count, error=error)

    def _loop(self) -> None:
        while self._running:
            self.scan()
            for _ in range(_POLL_INTERVAL_S):
                if not self._running:
                    return
                time.sleep(1)

    def _ingest(self, post: dict[str, str]) -> bool:
        text = post.get("text", "")
        tweet_id = post.get("id", "")
        if len(text) < 10 or not tweet_id:
            return False
        distress = is_distress(text)
        coords = extract_coords(text)
        snippet = re.sub(r"https?://\S+", "", text).strip()
        event = IntelEvent(
            id=f"x{tweet_id[-15:]}",
            type="twitter",
            severity=classify_severity(text) if distress else "low",
            lat=coords[0] if coords else None,
            lon=coords[1] if coords else None,
            title=f"Alarm Phone: {snippet[:120]}{'…' if len(snippet) > 120 else ''}",
            text=text[:600],
            url=post.get("url", ""),
            source="Alarm Phone",
            author="alarm_phone",
            timestamp_utc=post.get("created_at", ""),
            metadata={
                "tweet_id": tweet_id,
                "platform": "x",
                "source_policy": "official_site_embed",
                "transport": "first_party_html",
                "is_distress": distress,
                "verification_status": "unverified_public_source",
            },
        )
        return intel_store.add(event, dedup_key=f"x:{tweet_id}")
