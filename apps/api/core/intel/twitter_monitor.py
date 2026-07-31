# SPDX-License-Identifier: AGPL-3.0-or-later
"""Official X API monitor for public Mediterranean maritime reports."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Optional

from core.intel.geoextract import classify_severity, extract_coords, is_distress
from core.intel.ngo_registry import NGO_TWITTER_HANDLES
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

_SEARCH_QUERIES = [
    '(mayday OR "boat sinking" OR "taking water" OR capsized OR "people drowning" '
    'OR "man overboard") (Mediterranean OR Lampedusa OR Sicily OR Libya OR Malta '
    'OR Tunisia OR Aegean) -is:retweet',
    '(rescue OR "rescue operation" OR "SAR operation" OR "coast guard") '
    '(Mediterranean OR "central med" OR Lampedusa OR Malta) -is:retweet',
    '(naufragio OR annegamento OR dispersi OR "soccorso in mare" OR naufrage '
    'OR détresse OR غرق) (Mediterraneo OR Mediterranean OR Méditerranée '
    'OR Lampedusa OR Libya OR Malta) -is:retweet',
    "(" + " OR ".join(f"from:{handle}" for handle in NGO_TWITTER_HANDLES) + ")",
]

_X_API_BASE = "https://api.x.com/2/tweets/search/recent"
_TWEET_FIELDS = "created_at,text,author_id,geo,entities,public_metrics"
_EXPANSIONS = "author_id,geo.place_id"
_USER_FIELDS = "username,name"
_POLL_INTERVAL_S = 65


class TwitterMonitor:
    """Poll the official X API; no scraper or account-emulation fallback exists."""

    def __init__(self, bearer_token: str = "") -> None:
        self._bearer = bearer_token.strip()
        self._query_idx = 0
        self._since_id: dict[str, str] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def configured(self) -> bool:
        return bool(self._bearer)

    def start(self) -> None:
        if self._running:
            return
        if not self.configured:
            logger.info("X monitor disabled: official bearer token is not configured")
            return
        from core.intel.source_registry import source_registry

        source_registry.register("X / Twitter", "twitter")
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="intel-x-official",
        )
        self._thread.start()
        logger.info("Official X monitor started")

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        from core.intel.source_registry import source_registry

        while self._running:
            new_count = 0
            error: Optional[str] = None
            try:
                query = _SEARCH_QUERIES[self._query_idx % len(_SEARCH_QUERIES)]
                self._query_idx += 1
                for post in self._fetch(query):
                    if self._ingest(post, query):
                        new_count += 1
            except Exception as exc:
                error = str(exc)
                logger.warning("Official X monitor error: %s", exc)
            source_registry.record_poll("X / Twitter", events_found=new_count, error=error)
            time.sleep(_POLL_INTERVAL_S)

    def _fetch(self, query: str) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "query": query,
            "max_results": "20",
            "tweet.fields": _TWEET_FIELDS,
            "expansions": _EXPANSIONS,
            "user.fields": _USER_FIELDS,
        }
        since_id = self._since_id.get(query)
        if since_id:
            params["since_id"] = since_id

        request = urllib.request.Request(
            f"{_X_API_BASE}?{urllib.parse.urlencode(params)}",
            headers={
                "Authorization": f"Bearer {self._bearer}",
                "Accept": "application/json",
                "User-Agent": "SeaCommonsIntel/2.0",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read())

        users = {
            user["id"]: user.get("username", "")
            for user in payload.get("includes", {}).get("users", [])
        }
        posts = [
            {
                "id": post["id"],
                "text": post.get("text", ""),
                "created_at": post.get("created_at", ""),
                "author": users.get(post.get("author_id", ""), "unknown"),
                "url": f"https://x.com/i/web/status/{post['id']}",
            }
            for post in payload.get("data", [])
        ]
        if posts:
            self._since_id[query] = max(posts, key=lambda post: int(post["id"]))["id"]
        return posts

    def _ingest(self, post: dict[str, Any], query: str) -> bool:
        text = str(post.get("text") or "")
        if len(text) < 10:
            return False
        account_rule = "from:" in query
        distress = is_distress(text)
        if not distress and not account_rule:
            return False

        coords = extract_coords(text)
        severity = classify_severity(text)
        if not distress:
            severity = "low" if severity == "low" else "medium"
        author = str(post.get("author") or "")
        event = IntelEvent(
            type="twitter",
            severity=severity,
            lat=coords[0] if coords else None,
            lon=coords[1] if coords else None,
            title=_make_title(text, author),
            text=text[:500],
            url=str(post.get("url") or ""),
            source=author or "X",
            author=author,
            timestamp_utc=str(post.get("created_at") or ""),
            metadata={
                "tweet_id": str(post.get("id") or ""),
                "platform": "x",
                "source_policy": "official_api",
                "is_distress": distress,
            },
        )
        added = intel_store.add(event, dedup_key=f"x:{post.get('id', '')}")
        if added and distress:
            from core.intel.triangulation import evaluate as evaluate_triangulation
            evaluate_triangulation(event)
        return added


def _make_title(text: str, author: str) -> str:
    clean = re.sub(r"https?://\S+", "", text).strip()
    prefix = f"@{author}: " if author else ""
    snippet = clean[:80].rstrip()
    return f"{prefix}{snippet}{'…' if len(clean) > 80 else ''}"
