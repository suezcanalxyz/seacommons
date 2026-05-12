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
        self._iom_next_poll: float = 0.0
        self._rss_next_poll: float = 0.0

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

            event = IntelEvent(
                type="iom_incident",
                severity=severity,
                lat=lat,
                lon=lon,
                title=title,
                text=text,
                url=f"https://missingmigrants.iom.int/incident/{iid}",
                source="IOM Missing Migrants",
                metadata={
                    "incident_id": iid,
                    "dead": dead,
                    "missing": missing,
                    "survivors": survivors,
                    "incident_date": str(inc.get("incident_date", "")),
                    "location": location_text,
                    "cause": str(inc.get("cause_of_death", "")),
                },
            )
            if intel_store.add(event, dedup_key=f"iom:{iid}"):
                new += 1

        if new:
            logger.info("IOM: +%d new incidents", new)

    # ── RSS feeds ─────────────────────────────────────────────────────────────

    def _poll_rss_all(self) -> None:
        new = 0
        for feed in RSS_FEEDS:
            try:
                items = self._fetch_rss(feed["url"])
                for item in items:
                    if self._ingest_rss_item(item, feed["label"], feed["filter"]):
                        new += 1
            except Exception as exc:
                logger.debug("RSS %s failed: %s", feed["label"], exc)
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
        dedup = hashlib.sha1(f"{source}:{guid}".encode()).hexdigest()[:16]
        if dedup in self._rss_last_guids:
            return False
        self._rss_last_guids.add(dedup)
        if len(self._rss_last_guids) > 4000:
            self._rss_last_guids = set(list(self._rss_last_guids)[2000:])

        text = f"{item.get('title', '')} {item.get('description', '')}"
        text_clean = re.sub(r"<[^>]+>", " ", text).strip()

        if apply_filter and not _med_relevant(text_clean):
            return False

        coords = extract_coords(text_clean)
        severity = classify_severity(text_clean) if is_distress(text_clean) else "low"

        event = IntelEvent(
            type="news",
            severity=severity,
            lat=coords[0] if coords else None,
            lon=coords[1] if coords else None,
            title=item.get("title", "")[:200],
            text=text_clean[:600],
            url=item.get("link", ""),
            source=source,
            metadata={"pub_date": item.get("pub_date", "")},
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

            dedup = hashlib.sha1(text_raw[:120].encode()).hexdigest()[:16]
            if dedup in self._alarmphone_seen:
                continue
            self._alarmphone_seen.add(dedup)
            if len(self._alarmphone_seen) > 500:
                self._alarmphone_seen = set(list(self._alarmphone_seen)[250:])

            coords = extract_coords(text_raw)
            severity = classify_severity(text_raw)

            event = IntelEvent(
                type="news",
                severity=severity,
                lat=coords[0] if coords else None,
                lon=coords[1] if coords else None,
                title=f"Alarm Phone: {text_raw[:80]}…",
                text=text_raw[:600],
                url="https://alarmphone.org/en/calls/",
                source="Alarm Phone",
                metadata={"scrape_source": "alarmphone.org"},
            )
            if intel_store.add(event, dedup_key=dedup):
                new += 1

        if new:
            logger.info("Alarm Phone: +%d new calls", new)


# ── Helpers ───────────────────────────────────────────────────────────────────

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
