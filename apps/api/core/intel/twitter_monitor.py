# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Twitter/X maritime intelligence monitor.

Sources:
  - Official Twitter API v2 (recent search) — requires TWITTER_BEARER_TOKEN
  - twscrape (web API, open-source) — requires TWITTER_ACCOUNTS JSON config
  - Nitter RSS mirrors — zero-auth fallback

Priority: official API > twscrape > Nitter RSS.

The monitor polls in a background daemon thread; events are pushed to IntelStore.
Only tweets mentioning distress/SAR/rescue in or near the Mediterranean are kept.
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

from core.intel.geoextract import classify_severity, extract_coords, is_distress
from core.intel.ngo_registry import NGO_TWITTER_HANDLES
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

# ── Search configuration ──────────────────────────────────────────────────────

# Twitter API v2 recent search — up to 512 chars per query
_SEARCH_QUERIES = [
    # Distress at sea in the Mediterranean (English)
    '(mayday OR "boat sinking" OR distress OR "people drowning" OR capsized OR "man overboard") '
    '(Mediterranean OR Lampedusa OR Sicily OR Libya OR Malta OR Tunisia OR Aegean) -is:retweet',

    # SAR operations
    '(rescue OR "rescue operation" OR "SAR operation" OR "coast guard") '
    '(Mediterranean OR med sea OR Lampedusa OR "central med") -is:retweet',

    # Italian / French / Arabic keywords
    '(naufragio OR annegamento OR dispersi OR "soccorso in mare" OR naufrage OR détresse) '
    '-is:retweet lang:it lang:fr lang:ar',

    # Known NGO and monitoring accounts (any tweet they post is relevant)
    "(" + " OR ".join(f"from:{h}" for h in NGO_TWITTER_HANDLES) + ")",

    # Alarm Phone specific (always include regardless of lang)
    "from:alarm__phone",
]

# Nitter public instances (fallback, no auth)
_NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]

_TWITTER_API_BASE = "https://api.twitter.com/2/tweets/search/recent"
_TWEET_FIELDS = "created_at,text,author_id,geo,entities,public_metrics"
_EXPANSIONS = "author_id,geo.place_id"
_USER_FIELDS = "username,name"

# Rate: free tier allows ~1 req/sec; we poll once per POLL_INTERVAL_S
_POLL_INTERVAL_S = 65  # just over 1 minute to stay well within limits


class TwitterMonitor:
    """
    Polls Twitter for SAR-relevant tweets using available auth method.
    Runs in a daemon thread; call start() once.
    """

    def __init__(self, bearer_token: str = "", twscrape_accounts: str = "") -> None:
        self._bearer = bearer_token.strip()
        self._twscrape_cfg = twscrape_accounts.strip()
        self._query_idx = 0          # round-robin through search queries
        self._since_id: dict[str, str] = {}  # query → last tweet id
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._api = self._detect_api()

    def _detect_api(self) -> str:
        if self._bearer:
            return "official"
        if self._twscrape_cfg:
            return "twscrape"
        return "nitter"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="intel-twitter"
        )
        self._thread.start()
        logger.info("TwitterMonitor started (api=%s)", self._api)

    def stop(self) -> None:
        self._running = False

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        from core.intel.source_registry import source_registry
        source_registry.register("Twitter/X", "twitter")

        while self._running:
            new_count = 0
            error_str = None
            try:
                query = _SEARCH_QUERIES[self._query_idx % len(_SEARCH_QUERIES)]
                self._query_idx += 1
                tweets = self._fetch(query)
                for tw in tweets:
                    if self._ingest(tw, query):
                        new_count += 1
                if new_count:
                    logger.info("Twitter: +%d new intel events", new_count)
            except Exception as exc:
                logger.warning("Twitter monitor error: %s", exc)
                error_str = str(exc)
            source_registry.record_poll("Twitter/X", events_found=new_count, error=error_str)
            time.sleep(_POLL_INTERVAL_S)

    # ── Fetch strategies ──────────────────────────────────────────────────────

    def _fetch(self, query: str) -> list[dict[str, Any]]:
        if self._api == "official":
            return self._fetch_official(query)
        if self._api == "twscrape":
            return self._fetch_twscrape(query)
        return self._fetch_nitter(query)

    def _fetch_official(self, query: str) -> list[dict[str, Any]]:
        """Twitter API v2 recent search with Bearer token."""
        params: dict[str, str] = {
            "query": query,
            "max_results": "15",
            "tweet.fields": _TWEET_FIELDS,
            "expansions": _EXPANSIONS,
            "user.fields": _USER_FIELDS,
        }
        since_id = self._since_id.get(query)
        if since_id:
            params["since_id"] = since_id

        url = f"{_TWITTER_API_BASE}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._bearer}",
                "User-Agent": "SeacommonsIntel/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())

        tweets = data.get("data", [])
        # Build username lookup from includes
        includes = data.get("includes", {})
        users = {u["id"]: u.get("username", "") for u in includes.get("users", [])}

        results = []
        for tw in tweets:
            results.append({
                "id": tw["id"],
                "text": tw.get("text", ""),
                "created_at": tw.get("created_at", ""),
                "author": users.get(tw.get("author_id", ""), "unknown"),
                "url": f"https://twitter.com/i/web/status/{tw['id']}",
            })
        if results:
            self._since_id[query] = results[0]["id"]
        return results

    def _fetch_twscrape(self, query: str) -> list[dict[str, Any]]:
        """twscrape library (open-source, no official API key needed)."""
        try:
            import twscrape  # type: ignore[import]
        except ImportError:
            logger.warning("twscrape not installed — pip install twscrape")
            return []
        # twscrape is async; run in a new event loop for thread compat
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._twscrape_search(twscrape, query))
        finally:
            loop.close()

    @staticmethod
    async def _twscrape_search(twscrape, query: str) -> list[dict[str, Any]]:
        api = twscrape.API()
        results = []
        async for tw in api.search(query, limit=15):
            results.append({
                "id": str(tw.id),
                "text": tw.rawContent,
                "created_at": tw.date.isoformat() if tw.date else "",
                "author": tw.user.username if tw.user else "",
                "url": tw.url or "",
            })
        return results

    def _fetch_nitter(self, query: str) -> list[dict[str, Any]]:
        """
        Scrape Nitter RSS (zero-auth fallback).
        Nitter exposes /search?q=...&f=tweets as an RSS-like feed.
        Falls back to profile RSS for known handles.
        """
        results: list[dict[str, Any]] = []
        # For handle-specific queries ("from:alarm__phone"), use profile RSS
        handle_match = re.search(r"from:(\w+)", query)
        if handle_match:
            handle = handle_match.group(1)
            results.extend(self._nitter_profile_rss(handle))
        else:
            results.extend(self._nitter_search_rss(query))
        return results

    def _nitter_profile_rss(self, handle: str) -> list[dict[str, Any]]:
        for base in _NITTER_INSTANCES:
            try:
                url = f"{base}/{handle}/rss"
                req = urllib.request.Request(url, headers={"User-Agent": "SeacommonsIntel/1.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    xml = r.read().decode("utf-8", errors="replace")
                return _parse_rss_items(xml, source=handle)
            except Exception:
                continue
        return []

    def _nitter_search_rss(self, query: str) -> list[dict[str, Any]]:
        encoded = urllib.parse.quote_plus(query[:100])
        for base in _NITTER_INSTANCES:
            try:
                url = f"{base}/search?q={encoded}&f=tweets"
                req = urllib.request.Request(url, headers={"User-Agent": "SeacommonsIntel/1.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    html = r.read().decode("utf-8", errors="replace")
                # Extract tweet text from Nitter HTML (simple regex)
                items = re.findall(
                    r'class="tweet-content[^"]*"[^>]*>(.*?)</div>', html, re.S
                )
                return [
                    {
                        "id": str(hash(t)),
                        "text": re.sub(r"<[^>]+>", " ", t).strip(),
                        "created_at": "",
                        "author": "search",
                        "url": "",
                    }
                    for t in items[:15]
                ]
            except Exception:
                continue
        return []

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def _ingest(self, tweet: dict[str, Any], query: str) -> bool:
        text = tweet.get("text", "")
        if not text or len(text) < 10:
            return False

        # Filter: must contain distress/SAR keyword
        if not is_distress(text) and not _is_ngo_query(query):
            return False

        coords = extract_coords(text)
        severity = classify_severity(text)

        # NGO account posts default to 'medium' if no distress keyword found
        if not is_distress(text):
            severity = "low" if severity == "low" else "medium"

        author = tweet.get("author", "")
        title = _make_title(text, author)

        event = IntelEvent(
            type="twitter",
            severity=severity,
            lat=coords[0] if coords else None,
            lon=coords[1] if coords else None,
            title=title,
            text=text[:500],
            url=tweet.get("url", ""),
            source=author or "twitter",
            author=author,
            metadata={
                "tweet_id": tweet.get("id", ""),
                "query_bucket": query[:60],
            },
        )
        return intel_store.add(event)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_ngo_query(query: str) -> bool:
    return "from:" in query


def _make_title(text: str, author: str) -> str:
    clean = re.sub(r"https?://\S+", "", text).strip()
    prefix = f"@{author}: " if author else ""
    snippet = clean[:80].rstrip()
    return f"{prefix}{snippet}{'…' if len(clean) > 80 else ''}"


def _parse_rss_items(xml: str, source: str) -> list[dict[str, Any]]:
    """Minimal RSS item parser (no external lib required)."""
    items = re.findall(r"<item>(.*?)</item>", xml, re.S)
    results = []
    for item in items[:15]:
        title = _tag(item, "title")
        desc = _tag(item, "description")
        link = _tag(item, "link")
        pub = _tag(item, "pubDate")
        text = re.sub(r"<[^>]+>", " ", f"{title} {desc}").strip()
        results.append({
            "id": str(hash(text)),
            "text": text,
            "created_at": pub,
            "author": source,
            "url": link,
        })
    return results


def _tag(xml: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", xml, re.S)
    return (m.group(1) or "").strip() if m else ""
