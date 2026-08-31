# SPDX-License-Identifier: AGPL-3.0-or-later
"""
GDACS (Global Disaster Alert and Coordination System) monitor.

Free, public RSS feed — no API key, no account, no rate limit published.
https://www.gdacs.org/xml/rss.xml

GDACS is not a distress-call channel: it reports declared disasters (tropical
cyclones, floods, earthquakes, etc.) with a UN-coordinated alert level, not
individual boats in distress. It is ingested here as a *situational-awareness
and corroboration* signal only (e.g. a red-alert storm over the Central
Mediterranean the same day multiple crossing-distress reports come in), the
same role `news_monitor.py`'s RSS feeds and the IOM archive play. It never
appears in the public Live feed (see `core.live.projection._PUBLIC_INTEL_TYPES`)
since it does not represent a direct distress call.

Runs in a background daemon thread; events are pushed to IntelStore.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 20 * 60
_FEED_URL = "https://www.gdacs.org/xml/rss.xml"
_HEADERS = {
    "User-Agent": "SeacommonsIntel/1.0 (open-source SAR dashboard)",
    "Accept": "application/rss+xml, application/xml, */*",
}

# Roughly the Mediterranean basin — same bounding box used by
# core.vessels.aisstream for AIS coverage, so GDACS events are kept relevant
# to the project's operating theatre rather than ingesting disasters globally.
_LAT_MIN, _LAT_MAX = 28.0, 47.0
_LON_MIN, _LON_MAX = -6.0, 42.0

_ALERT_SEVERITY = {"red": "critical", "orange": "medium", "green": "low"}


class GDACSMonitor:
    """Polls the public GDACS RSS feed for disaster alerts near the Mediterranean."""

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._seen: set[str] = set()
        self._seen_lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="intel-gdacs")
        self._thread.start()
        logger.info("GDACSMonitor started")

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        from core.intel.source_registry import source_registry
        source_registry.register("GDACS", "rss")

        while self._running:
            new_total = 0
            error_str: Optional[str] = None
            try:
                request = urllib.request.Request(_FEED_URL, headers=_HEADERS)
                with urllib.request.urlopen(request, timeout=15) as response:
                    xml = response.read().decode("utf-8", errors="replace")
                for item in _parse_gdacs_rss(xml):
                    if self._ingest(item):
                        new_total += 1
            except Exception as exc:
                error_str = str(exc)
                logger.debug("GDACS feed failed: %s", exc)

            source_registry.record_poll("GDACS", events_found=new_total, error=error_str)
            if new_total:
                logger.info("GDACS: +%d new intel events", new_total)
            time.sleep(_POLL_INTERVAL_S)

    def _ingest(self, item: dict[str, str]) -> bool:
        identity = item.get("guid") or item.get("link") or item.get("title") or ""
        dedup = hashlib.blake2s(f"gdacs:{identity}".encode(), digest_size=8).hexdigest()

        with self._seen_lock:
            if dedup in self._seen:
                return False
            self._seen.add(dedup)
            if len(self._seen) > 2000:
                self._seen = set(list(self._seen)[1000:])

        lat, lon = item.get("lat"), item.get("lon")
        if lat is None or lon is None:
            return False
        try:
            lat_f, lon_f = float(lat), float(lon)
        except ValueError:
            return False
        if not (_LAT_MIN <= lat_f <= _LAT_MAX and _LON_MIN <= lon_f <= _LON_MAX):
            return False

        alert_level = (item.get("alertlevel") or "").strip().lower()
        severity = _ALERT_SEVERITY.get(alert_level, "low")
        event_type = item.get("eventtype", "")
        title = item.get("title", "")[:200] or f"GDACS {event_type} alert"

        event = IntelEvent(
            id=dedup,
            type="gdacs",
            severity=severity,
            lat=lat_f,
            lon=lon_f,
            title=title,
            text=item.get("description", "")[:600],
            url=item.get("link", ""),
            source="GDACS",
            timestamp_utc=_parse_date(item.get("pub_date", "")),
            metadata={
                "source_policy": "official_rss",
                "transport": "rss",
                "gdacs_event_type": event_type,
                "gdacs_alert_level": alert_level,
                "gdacs_country": item.get("country", ""),
            },
        )
        return intel_store.add(event, dedup_key=dedup)


# ── RSS / GeoRSS parsing ────────────────────────────────────────────────────

def _parse_date(raw: str) -> str:
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    import email.utils
    try:
        return email.utils.parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _xml_tag(xml: str, tag: str) -> str:
    match = re.search(
        rf"<{tag}\b[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>",
        xml,
        re.S | re.I,
    )
    return (match.group(1) or "").strip() if match else ""


def _parse_gdacs_rss(xml: str) -> list[dict[str, str]]:
    """Parse GDACS RSS items, including their geo:Point / georss:point coordinates."""
    raw_items = re.findall(r"<item\b[^>]*>(.*?)</item>", xml, re.S | re.I)
    out: list[dict[str, str]] = []
    for item in raw_items[:50]:
        lat = _xml_tag(item, "geo:lat")
        lon = _xml_tag(item, "geo:long") or _xml_tag(item, "geo:lon")
        if not lat or not lon:
            point = _xml_tag(item, "georss:point")
            parts = point.split()
            if len(parts) == 2:
                lat, lon = parts[0], parts[1]
        out.append({
            "title": _xml_tag(item, "title"),
            "description": _xml_tag(item, "description"),
            "link": _xml_tag(item, "link"),
            "guid": _xml_tag(item, "guid"),
            "pub_date": _xml_tag(item, "pubDate"),
            "lat": lat,
            "lon": lon,
            "alertlevel": _xml_tag(item, "gdacs:alertlevel"),
            "eventtype": _xml_tag(item, "gdacs:eventtype"),
            "country": _xml_tag(item, "gdacs:country"),
        })
    return out
