# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bluesky (AT Protocol) monitor for public Mediterranean maritime reports.

Uses Bluesky's public AppView search endpoint — no account, no API key, no
OAuth. `public.api.bsky.app` serves unauthenticated reads of public posts,
mirroring the role the official X API plays in `twitter_monitor.py` but on a
decentralized, free platform (added as a second, independent "parallel to
Twitter" channel rather than a replacement for it).

API endpoint: https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts

Runs in a background daemon thread; events are pushed to IntelStore.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Optional

from core.intel.geoextract import classify_severity, extract_coords, is_distress
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

_SEARCH_QUERIES = [
    "mayday boat sinking Mediterranean",
    "rescue Lampedusa Libya Malta migrants",
    "naufragio dispersi soccorso mare",
]

_API_BASE = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
_HEADERS = {
    "User-Agent": "SeacommonsIntel/1.0 (open-source SAR dashboard)",
    "Accept": "application/json",
}
_POLL_INTERVAL_S = 5 * 60


class BlueskyMonitor:
    """Poll Bluesky's public search API for Mediterranean distress-relevant posts."""

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._query_idx = 0
        self._seen: set[str] = set()
        self._seen_lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="intel-bluesky")
        self._thread.start()
        logger.info("BlueskyMonitor started")

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        from core.intel.source_registry import source_registry
        source_registry.register("Bluesky", "bluesky")

        while self._running:
            query = _SEARCH_QUERIES[self._query_idx % len(_SEARCH_QUERIES)]
            self._query_idx += 1
            new_total = 0
            error_str: Optional[str] = None
            try:
                posts = self._search(query)
                for post in posts:
                    if self._ingest(post):
                        new_total += 1
            except Exception as exc:
                error_str = str(exc)
                logger.debug("Bluesky search failed (%s): %s", query, exc)

            source_registry.record_poll("Bluesky", events_found=new_total, error=error_str)
            if new_total:
                logger.info("Bluesky: +%d new intel events", new_total)
            time.sleep(_POLL_INTERVAL_S)

    def _search(self, query: str) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode({"q": query, "limit": 25, "sort": "latest"})
        url = f"{_API_BASE}?{params}"
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        return data.get("posts", [])

    def _ingest(self, post: dict[str, Any]) -> bool:
        uri = post.get("uri", "")
        if not uri:
            return False
        dedup_key = f"bluesky:{uri}"

        with self._seen_lock:
            if dedup_key in self._seen:
                return False
            self._seen.add(dedup_key)
            if len(self._seen) > 3000:
                self._seen = set(list(self._seen)[1500:])

        record = post.get("record", {}) or {}
        text = (record.get("text") or "").strip()
        if not text or len(text) < 15:
            return False
        if not is_distress(text):
            return False

        coords = extract_coords(text)
        severity = classify_severity(text)
        author = post.get("author", {}) or {}
        handle = author.get("handle", "")

        # Bluesky's at:// URI (at://did/collection/rkey) maps to a bsky.app permalink.
        rkey = uri.rsplit("/", 1)[-1]
        permalink = f"https://bsky.app/profile/{handle}/post/{rkey}" if handle else ""

        title_text = text[:120].rstrip()
        title = f"@{handle}: {title_text}{'…' if len(text) > 120 else ''}"
        event_type = "distress" if severity in ("critical", "high") else "bluesky"

        event = IntelEvent(
            type=event_type,
            severity=severity,
            lat=coords[0] if coords else None,
            lon=coords[1] if coords else None,
            title=title,
            text=text[:600],
            url=permalink,
            source="Bluesky",
            author=handle,
            timestamp_utc=record.get("createdAt", ""),
            metadata={
                "platform": "bluesky",
                "uri": uri,
                "source_policy": "official_api",
            },
        )
        added = intel_store.add(event, dedup_key=dedup_key)
        if added and event_type == "distress":
            from core.intel.triangulation import evaluate as evaluate_triangulation
            evaluate_triangulation(event)
        return added
