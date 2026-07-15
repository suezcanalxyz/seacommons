# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Maritime news and incident feed monitor.

Sources (all public, no credentials required unless noted):
  1. IOM Missing Migrants Project API (public JSON)
  2. UNHCR news RSS
  3. InfoMigrants RSS
  4. ReliefWeb RSS (Mediterranean filter)
  5. MarineTraffic blog RSS
  6. Alarm Phone calls page (HTML scrape)
  7. Watch The Med incident reports (HTML scrape)

Runs in a background daemon thread; events pushed to IntelStore.
"""
from __future__ import annotations

import email.utils
import hashlib
import json
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

from core.intel.geoextract import classify_severity, extract_coords, is_distress
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 5 * 60   # every 5 minutes (RSS feeds don't update faster)
_IOM_POLL_INTERVAL_S = 15 * 60  # IOM API every 15 minutes

_HEADERS = {
    "User-Agent": "SeacommonsIntel/1.0 (open-source SAR dashboard)",
    "Accept": "application/json, text/html, application/rss+xml, */*",
}

# Mediterranean distress keyword filter for generic RSS feeds
_MED_FILTER_KW = frozenset([
    "mediterranean", "lampedusa", "sicily", "libya", "tunisia", "malta",
    "migrant", "migrants", "asylum", "refugee", "distress", "rescue",
    "naufragio", "naufrage", "méditerranée", "sauvetage", "mare nostrum",
    "aegean", "lesvos", "chios", "drowning", "shipwreck", "boat",
])

# ── RSS feed definitions ───────────────────────────────────────────────────────

# Nitter instances provide Twitter accounts as public RSS without API keys.
# We try each in order; the first that responds is used.
_NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
]

# High-value distress-focused Twitter accounts to monitor via Nitter RSS
_TWITTER_ACCOUNTS = [
    {"handle": "alarmphone",     "label": "Alarm Phone",      "filter": False},
    {"handle": "alarm_phone",    "label": "Alarm Phone",      "filter": False},
    {"handle": "SOSMedIntl",     "label": "SOS Méditerranée", "filter": False},
    {"handle": "SeaWatchItaly",  "label": "Sea Watch",        "filter": False},
    {"handle": "MSF_Sea",        "label": "MSF Sea",          "filter": False},
    {"handle": "WatchTheMed",    "label": "Watch The Med",    "filter": False},
]

RSS_FEEDS = [
    {
        "url": "https://www.unhcr.org/rss/news.rss",
        "label": "UNHCR",
        "filter": True,   # only keep items matching _MED_FILTER_KW
    },
    {
        "url": "https://www.infomigrants.net/en/rss",
        "label": "InfoMigrants",
        "filter": False,  # all items are relevant (migration-focused outlet)
    },
    {
        "url": "https://reliefweb.int/updates/rss.xml",
        "label": "ReliefWeb",
        "filter": True,
    },
    {
        "url": "https://www.marinetraffic.com/blog/feed/",
        "label": "MarineTraffic",
        "filter": True,
    },
    {
        "url": "https://sea-watch.org/en/feed/",
        "label": "Sea Watch",
        "filter": False,
    },
    {
        "url": "https://www.sosmediterranee.org/feed/",
        "label": "SOS Méditerranée",
        "filter": False,
    },
    {
        "url": "https://emergency.it/feed/",
        "label": "Emergency ONG",
        "filter": True,
    },
]


class NewsMonitor:
    """Polls open news/incident sources for maritime emergencies."""

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._iom_last_ids: set[str] = set()
        self._rss_last_guids: set[str] = set()
        self._alarmphone_seen: set[str] = set()
        self._twitter_seen: set[str] = set()
        self._iom_next_poll: float = 0.0
        self._rss_next_poll: float = 0.0
        self._twitter_next_poll: float = 0.0
        self._nitter_base: Optional[str] = None  # cached working instance

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="intel-news"
        )
        self._thread.start()
        logger.info("NewsMonitor started")

    def stop(self) -> None:
        self._running = False

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        from core.intel.source_registry import source_registry
        source_registry.register("IOM Missing Migrants", "rss")
        source_registry.register("RSS Feeds", "rss")
        source_registry.register("Alarm Phone", "scrape")
        source_registry.register("Nitter/Twitter RSS", "rss")

        while self._running:
            now = time.monotonic()
            try:
                if now >= self._iom_next_poll:
                    self._poll_iom()
                    self._iom_next_poll = now + _IOM_POLL_INTERVAL_S
                if now >= self._rss_next_poll:
                    self._poll_rss_all()
                    self._poll_alarmphone()
                    self._rss_next_poll = now + _POLL_INTERVAL_S
                if now >= self._twitter_next_poll:
                    self._poll_twitter_accounts()
                    self._twitter_next_poll = now + _POLL_INTERVAL_S
            except Exception as exc:
                logger.warning("NewsMonitor error: %s", exc)
            time.sleep(30)

    # ── IOM Missing Migrants ──────────────────────────────────────────────────

    def _poll_iom(self) -> None:
        """
        IOM Missing Migrants Project — public API, no auth.
        Returns verified Mediterranean incidents.
        """
        url = (
            "https://missingmigrants.iom.int/api/incidents"
            "?route=Mediterranean&status=Verified&page=1&per_page=50"
        )
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
        except Exception as exc:
            logger.debug("IOM API failed: %s", exc)
            return

        incidents = data if isinstance(data, list) else data.get("data", [])
        new = 0
        for inc in incidents:
            iid = str(inc.get("id", ""))
            if iid in self._iom_last_ids:
                continue
            self._iom_last_ids.add(iid)

            lat = _safe_float(inc.get("latitude") or inc.get("lat"))
            lon = _safe_float(inc.get("longitude") or inc.get("lon"))

            # Try text extraction if explicit coords absent
            location_text = str(inc.get("location_of_incident", ""))
            if lat is None or lon is None:
                coords = extract_coords(location_text)
                if coords:
                    lat, lon = coords

            dead = int(inc.get("number_dead", 0) or 0)
            missing = int(inc.get("number_missing", 0) or 0)
            survivors = int(inc.get("number_survivors", 0) or 0)

            title = inc.get("title") or f"IOM incident — {location_text[:60]}"
            text = (
                f"{title}. "
                f"Dead: {dead}, Missing: {missing}, Survivors: {survivors}. "
                f"Date: {inc.get('incident_date', 'unknown')}."
            )

            severity = "critical" if (dead + missing) > 5 else "high" if (dead + missing) > 0 else "medium"

            incident_date_raw = str(inc.get("incident_date", ""))
            event = IntelEvent(
                type="iom_incident",
                severity=severity,
                lat=lat,
                lon=lon,
                title=title,
                text=text,
                url=f"https://missingmigrants.iom.int/incident/{iid}",
                source="IOM Missing Migrants",
                timestamp_utc=_parse_date(incident_date_raw),
                metadata={
                    "incident_id": iid,
                    "dead": dead,
                    "missing": missing,
                    "survivors": survivors,
                    "incident_date": incident_date_raw,
                    "location": location_text,
                    "cause": str(inc.get("cause_of_death", "")),
                },
            )
            if intel_store.add(event, dedup_key=f"iom:{iid}"):
                new += 1

        from core.intel.source_registry import source_registry
        source_registry.record_poll("IOM Missing Migrants", events_found=new)
        if new:
            logger.info("IOM: +%d new incidents", new)

    # ── RSS feeds ─────────────────────────────────────────────────────────────

    def _poll_rss_all(self) -> None:
        from core.intel.source_registry import source_registry
        new = 0
        error_str = None
        for feed in RSS_FEEDS:
            try:
                items = self._fetch_rss(feed["url"])
                for item in items:
                    if self._ingest_rss_item(item, feed["label"], feed["filter"]):
                        new += 1
            except Exception as exc:
                logger.debug("RSS %s failed: %s", feed["label"], exc)
                error_str = str(exc)
        source_registry.record_poll("RSS Feeds", events_found=new, error=error_str)
        if new:
            logger.info("RSS feeds: +%d new intel events", new)

    def _fetch_rss(self, url: str) -> list[dict[str, Any]]:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            xml = r.read().decode("utf-8", errors="replace")
        return _parse_rss(xml)

    def _ingest_rss_item(
        self, item: dict[str, Any], source: str, apply_filter: bool
    ) -> bool:
        guid = item.get("guid") or item.get("link") or item.get("title", "")
        dedup = hashlib.blake2s(f"{source}:{guid}".encode(), digest_size=8).hexdigest()
        if dedup in self._rss_last_guids:
            return False
        self._rss_last_guids.add(dedup)
        if len(self._rss_last_guids) > 4000:
            self._rss_last_guids = set(list(self._rss_last_guids)[2000:])

        text = f"{item.get('title', '')} {item.get('description', '')}"
        text_clean = re.sub(r"<[^>]+>", " ", text).strip()
        text_clean = re.sub(r"\s+", " ", text_clean)

        if apply_filter and not _med_relevant(text_clean):
            return False

        distress = is_distress(text_clean)
        coords = extract_coords(text_clean)
        severity = classify_severity(text_clean) if distress else "low"
        event_type = "distress" if distress and severity in ("critical", "high") else "news"

        # Use the most specific URL available.
        # Prefer item <link> if it looks like an article URL (not just a homepage).
        # Fall back to guid if it looks like a URL, then empty string.
        item_link = item.get("link", "").strip()
        item_guid = item.get("guid", "").strip()
        url = _best_url(item_link, item_guid)

        pub_date_raw = item.get("pub_date", "")
        event = IntelEvent(
            type=event_type,
            severity=severity,
            lat=coords[0] if coords else None,
            lon=coords[1] if coords else None,
            title=item.get("title", "")[:200],
            text=text_clean[:600],
            url=url,
            source=source,
            timestamp_utc=_parse_date(pub_date_raw),
            metadata={"pub_date": pub_date_raw},
        )
        return intel_store.add(event, dedup_key=dedup)

    # ── Twitter / Nitter RSS ──────────────────────────────────────────────────

    def _get_nitter_base(self) -> Optional[str]:
        """
        Find a working Nitter instance. Tries instances in order and caches
        the first one that responds with HTTP 200. Re-validates if cached
        instance stops working.
        """
        for base in _NITTER_INSTANCES:
            try:
                req = urllib.request.Request(f"{base}/alarmphone/rss", headers=_HEADERS)
                with urllib.request.urlopen(req, timeout=8) as r:
                    if r.status == 200:
                        return base
            except Exception:
                continue
        return None

    def _poll_twitter_accounts(self) -> None:
        """
        Poll key distress-focused Twitter accounts via Nitter RSS.
        For each tweet that looks like a distress signal:
          1. Extract coords from tweet text
          2. Extract coords from embedded map/image (Vision fallback)
          3. Ingest as IntelEvent type="twitter"
        """
        if not self._nitter_base:
            self._nitter_base = self._get_nitter_base()
        if not self._nitter_base:
            logger.debug("No working Nitter instance found; Twitter polling skipped")
            return

        new = 0
        for acct in _TWITTER_ACCOUNTS:
            try:
                url = f"{self._nitter_base}/{acct['handle']}/rss"
                req = urllib.request.Request(url, headers=_HEADERS)
                with urllib.request.urlopen(req, timeout=12) as r:
                    xml = r.read().decode("utf-8", errors="replace")
                items = _parse_rss(xml)
                for item in items:
                    if self._ingest_twitter_item(item, acct["label"], acct["filter"]):
                        new += 1
            except Exception as exc:
                logger.debug("Nitter @%s failed: %s — resetting instance", acct["handle"], exc)
                self._nitter_base = None  # force re-discover on next cycle
                break

        from core.intel.source_registry import source_registry
        source_registry.record_poll("Nitter/Twitter RSS", events_found=new)
        if new:
            logger.info("Twitter/Nitter: +%d new distress signals", new)

    def _ingest_twitter_item(self, item: dict[str, Any], source: str, apply_filter: bool) -> bool:
        """
        Parse a tweet RSS item. Extracts coords from text first, then falls
        back to Vision extraction on any embedded image URL found in the description.
        """
        guid = item.get("guid") or item.get("link") or item.get("title", "")
        dedup = hashlib.blake2s(f"twitter:{source}:{guid}".encode(), digest_size=8).hexdigest()
        if dedup in self._twitter_seen:
            return False
        self._twitter_seen.add(dedup)
        if len(self._twitter_seen) > 2000:
            self._twitter_seen = set(list(self._twitter_seen)[1000:])

        raw_desc = item.get("description", "")
        text_clean = re.sub(r"<[^>]+>", " ", f"{item.get('title', '')} {raw_desc}").strip()
        text_clean = re.sub(r"\s+", " ", text_clean)

        if apply_filter and not _med_relevant(text_clean):
            return False
        if not is_distress(text_clean) and not _med_relevant(text_clean):
            return False

        coords = extract_coords(text_clean)
        severity = classify_severity(text_clean)
        event_type = "distress" if severity in ("critical", "high") else "twitter"

        # If no coords from text, try Vision extraction on embedded images
        if coords is None:
            img_urls = _extract_img_urls(raw_desc)
            for img_url in img_urls[:2]:  # try at most 2 images
                vision_result = _vision_extract_sync(img_url)
                if vision_result:
                    coords = (vision_result["lat"], vision_result["lon"])
                    logger.info("Twitter Vision coords from %s: %s → %s", source, img_url, coords)
                    break

        item_link = item.get("link", "").strip()
        item_guid = item.get("guid", "").strip()
        url = _best_url(item_link, item_guid)

        pub_date_raw = item.get("pub_date", "")
        event = IntelEvent(
            type=event_type,
            severity=severity,
            lat=coords[0] if coords else None,
            lon=coords[1] if coords else None,
            title=item.get("title", "")[:200],
            text=text_clean[:600],
            url=item.get("link", ""),
            source=source,
            timestamp_utc=_parse_date(pub_date_raw),
            metadata={
                "pub_date": pub_date_raw,
                "platform": "twitter",
                "via": "nitter",
            },
        )
        return intel_store.add(event, dedup_key=dedup)

    # ── Alarm Phone scrape ────────────────────────────────────────────────────

    def _poll_alarmphone(self) -> None:
        """
        Scrape the Alarm Phone public calls log.
        URL: https://alarmphone.org/en/calls/
        Each call is listed with date, region, and usually coordinates.
        """
        try:
            req = urllib.request.Request(
                "https://alarmphone.org/en/calls/", headers=_HEADERS
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                html = r.read().decode("utf-8", errors="replace")
        except Exception as exc:
            logger.debug("Alarm Phone scrape failed: %s", exc)
            return

        # Extract call entries from the page
        # Alarm Phone HTML has entries with class "call-entry" or similar
        entries = re.findall(
            r'<(?:article|div|li)[^>]*class="[^"]*call[^"]*"[^>]*>(.*?)</(?:article|div|li)>',
            html, re.S
        )
        if not entries:
            # Fallback: grab any paragraph that looks like a distress report
            entries = re.findall(r"<p[^>]*>(.*?)</p>", html, re.S)

        new = 0
        for entry in entries[:30]:
            text_raw = re.sub(r"<[^>]+>", " ", entry).strip()
            text_raw = re.sub(r"\s+", " ", text_raw)
            if len(text_raw) < 30:
                continue
            if not is_distress(text_raw) and "alarm" not in text_raw.lower():
                continue

            dedup = hashlib.blake2s(text_raw[:120].encode(), digest_size=8).hexdigest()
            if dedup in self._alarmphone_seen:
                continue
            self._alarmphone_seen.add(dedup)
            if len(self._alarmphone_seen) > 500:
                self._alarmphone_seen = set(list(self._alarmphone_seen)[250:])

            coords = extract_coords(text_raw)
            severity = classify_severity(text_raw)

            # Try to extract date from the text (Alarm Phone uses DD/MM/YYYY or Month DD)
            date_match = re.search(r'\b(\d{1,2}[./]\d{1,2}[./]\d{2,4}|\w+ \d{1,2},? \d{4})\b', text_raw)
            ts = _parse_date(date_match.group(1) if date_match else "")
            # Try to extract a direct call-report URL from HTML links in the entry
            call_url = "https://alarmphone.org/en/calls/"
            url_match = re.search(r'href="(https://alarmphone\.org/en/calls/[^"]+)"', entry)
            if url_match:
                call_url = url_match.group(1)
            event = IntelEvent(
                type="distress",
                severity=severity,
                lat=coords[0] if coords else None,
                lon=coords[1] if coords else None,
                title=f"Alarm Phone: {text_raw[:80]}…",
                text=text_raw[:600],
                url=call_url,
                source="Alarm Phone",
                timestamp_utc=ts,
                metadata={"scrape_source": "alarmphone.org"},
            )
            if intel_store.add(event, dedup_key=dedup):
                new += 1

        from core.intel.source_registry import source_registry
        source_registry.record_poll("Alarm Phone", events_found=new)
        if new:
            logger.info("Alarm Phone: +%d new calls", new)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(raw: str) -> str:
    """
    Parse any common date string to ISO-8601 UTC.
    Accepts: RFC 2822 (RSS pubDate), ISO 8601, date-only strings.
    Falls back to now() if unparseable.
    """
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    raw = raw.strip()
    # RFC 2822: "Wed, 13 May 2026 12:28:33 +0000"
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    # ISO 8601 / date-only
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(raw[:len(fmt) + 4], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return datetime.now(timezone.utc).isoformat()


def _med_relevant(text: str) -> bool:
    tl = text.lower()
    return any(kw in tl for kw in _MED_FILTER_KW)


def _safe_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if f != 0.0 else None
    except (TypeError, ValueError):
        return None


def _parse_rss(xml: str) -> list[dict[str, Any]]:
    """Minimal RSS/Atom parser without external deps."""
    items: list[dict[str, Any]] = []
    # Try RSS <item> first, then Atom <entry>
    raw_items = re.findall(r"<item>(.*?)</item>", xml, re.S)
    if not raw_items:
        raw_items = re.findall(r"<entry>(.*?)</entry>", xml, re.S)
    for raw in raw_items[:20]:
        items.append({
            "title": _xml_tag(raw, "title"),
            "description": _xml_tag(raw, "description") or _xml_tag(raw, "summary"),
            "link": _xml_tag(raw, "link") or _xml_attr(raw, "link", "href"),
            "guid": _xml_tag(raw, "guid") or _xml_tag(raw, "id"),
            "pub_date": _xml_tag(raw, "pubDate") or _xml_tag(raw, "published"),
        })
    return items


def _xml_tag(xml: str, tag: str) -> str:
    m = re.search(
        rf"<{tag}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", xml, re.S
    )
    return (m.group(1) or "").strip() if m else ""


def _xml_attr(xml: str, tag: str, attr: str) -> str:
    m = re.search(rf'<{tag}[^>]*{attr}="([^"]+)"', xml)
    return m.group(1).strip() if m else ""


def _best_url(link: str, guid: str) -> str:
    """
    Return the most specific URL for an RSS item.
    Rejects generic homepage links (no path or just '/').
    Falls back to guid if it looks like a real article URL, else empty string.
    """
    def _is_article_url(u: str) -> bool:
        if not u or not u.startswith("http"):
            return False
        # Strip scheme and host — if path is empty or just '/', it's a homepage
        try:
            path = u.split("://", 1)[1].split("/", 1)[1] if "/" in u.split("://", 1)[1] else ""
        except IndexError:
            return False
        return len(path.strip("/")) > 3  # at least 3 chars of actual path

    if _is_article_url(link):
        return link
    if _is_article_url(guid):
        return guid
    return link  # return whatever we have, even if it's a homepage


def _extract_img_urls(html: str) -> list[str]:
    """
    Extract image URLs from RSS description HTML.
    Nitter embeds tweet images as <img src="..."> inside the description CDATA.
    """
    return re.findall(r'<img[^>]+src="([^"]+)"', html)


def _vision_extract_sync(img_url: str) -> Optional[dict[str, Any]]:
    """
    Synchronous wrapper around the async Vision extractor.
    Safe to call from background threads.  Returns None on any error.
    """
    try:
        import asyncio
        from core.intel.vision import extract_from_url
        return asyncio.run(extract_from_url(img_url))
    except Exception as exc:
        logger.debug("Vision extract failed for %s: %s", img_url, exc)
        return None
