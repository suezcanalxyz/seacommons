# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Approved public-source collectors.

IOM incidents are retained for archive/corroboration and never projected into
the Live feed. Only curated first-party NGO RSS feeds can produce public Live
observations. Unofficial social mirrors and HTML scraping are not supported.
"""
from __future__ import annotations

import email.utils
import hashlib
import html
import json
import logging
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

from core.intel.geoextract import (
    classify_severity,
    extract_coords,
    extract_numeric_coords,
    extract_relative_coords,
    is_direct_distress_call,
)
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 5 * 60
_IOM_POLL_INTERVAL_S = 15 * 60
_HEADERS = {
    "User-Agent": "SeaCommonsIntel/2.0 (official sources only)",
    "Accept": "application/json, application/rss+xml, application/atom+xml, */*",
}
_RSS_EMERGENCY_MARKER_RE = re.compile(
    r"(?:🆘|\bmayday\b|\bsos\b"
    r"(?!\s+(?:m[eé]diterran[eé]e|mediterranee|humanity)\b))",
    re.I,
)

RSS_FEEDS = [
    {
        "url": "https://alarmphone.org/en/feed/",
        "label": "Alarm Phone",
    },
    {
        "url": "https://sea-watch.org/en/feed/",
        "label": "Sea Watch",
    },
    {
        "url": "https://www.sosmediterranee.org/feed/",
        "label": "SOS Méditerranée",
    },
]


class NewsMonitor:
    """Collect archive incidents and first-party NGO RSS publications."""

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._iom_last_ids: set[str] = set()
        self._rss_last_guids: set[str] = set()
        self._iom_next_poll = 0.0
        self._rss_next_poll = 0.0

    def start(self) -> None:
        if self._running:
            return
        from core.intel.source_registry import source_registry

        source_registry.register("IOM Missing Migrants", "archive")
        source_registry.register("Official NGO RSS", "rss")
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="intel-approved-rss",
        )
        self._thread.start()
        logger.info("Approved public-source monitor started")

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            now = time.monotonic()
            if now >= self._iom_next_poll:
                self._poll_iom()
                self._iom_next_poll = now + _IOM_POLL_INTERVAL_S
            if now >= self._rss_next_poll:
                self._poll_rss_all()
                self._rss_next_poll = now + _POLL_INTERVAL_S
            time.sleep(30)

    def scan(self) -> None:
        """Refresh approved RSS sources; used by the process scheduler."""
        self._poll_rss_all()

    def _poll_iom(self) -> None:
        from core.intel.source_registry import source_registry

        new_count = 0
        error: Optional[str] = None
        try:
            request = urllib.request.Request(
                "https://missingmigrants.iom.int/api/incidents"
                "?route=Mediterranean&status=Verified&page=1&per_page=50",
                headers=_HEADERS,
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read())
            incidents = payload if isinstance(payload, list) else payload.get("data", [])
            for incident in incidents:
                incident_id = str(
                    incident.get("id")
                    or incident.get("incident_id")
                    or hashlib.blake2s(
                        json.dumps(incident, sort_keys=True).encode(),
                        digest_size=8,
                    ).hexdigest()
                )
                if incident_id in self._iom_last_ids:
                    continue
                self._iom_last_ids.add(incident_id)
                lat = _safe_float(incident.get("latitude") or incident.get("lat"))
                lon = _safe_float(incident.get("longitude") or incident.get("lon"))
                dead = int(incident.get("dead") or incident.get("number_dead") or 0)
                missing = int(incident.get("missing") or incident.get("number_missing") or 0)
                total = dead + missing
                severity = "critical" if total > 50 else "high" if total > 10 else "medium"
                date_value = str(incident.get("date") or incident.get("incident_date") or "")
                title = str(
                    incident.get("title")
                    or incident.get("incident_type")
                    or "Verified Mediterranean incident"
                )
                event = IntelEvent(
                    id=incident_id[:64],
                    type="iom_incident",
                    severity=severity,
                    lat=lat,
                    lon=lon,
                    title=f"IOM: {title}",
                    text=f"Dead: {dead} · Missing: {missing}",
                    url=str(incident.get("url") or "https://missingmigrants.iom.int/"),
                    source="IOM Missing Migrants",
                    timestamp_utc=_parse_date(date_value),
                    metadata={
                        "incident_id": incident_id,
                        "dead": dead,
                        "missing": missing,
                        "source_policy": "archive",
                    },
                )
                if intel_store.add(event, dedup_key=f"iom:{incident_id}"):
                    new_count += 1
        except Exception as exc:
            error = str(exc)
            logger.debug("IOM archive pull failed: %s", exc)
        source_registry.record_poll(
            "IOM Missing Migrants",
            events_found=new_count,
            error=error,
        )

    def _poll_rss_all(self) -> None:
        from core.intel.source_registry import source_registry

        new_count = 0
        errors: list[str] = []
        for feed in RSS_FEEDS:
            try:
                request = urllib.request.Request(feed["url"], headers=_HEADERS)
                with urllib.request.urlopen(request, timeout=15) as response:
                    items = _parse_rss(response.read().decode("utf-8", errors="replace"))
                for item in items:
                    if self._ingest_rss_item(item, feed["label"]):
                        new_count += 1
            except Exception as exc:
                errors.append(f"{feed['label']}: {exc}")
                logger.debug("Official RSS %s failed: %s", feed["label"], exc)
        source_registry.record_poll(
            "Official NGO RSS",
            events_found=new_count,
            error="; ".join(errors) if errors else None,
        )

    def _ingest_rss_item(self, item: dict[str, str], source: str) -> bool:
        identity = item.get("guid") or item.get("link") or item.get("title") or ""
        dedup = hashlib.blake2s(f"{source}:{identity}".encode(), digest_size=8).hexdigest()
        if dedup in self._rss_last_guids:
            return False
        self._rss_last_guids.add(dedup)
        if len(self._rss_last_guids) > 4000:
            self._rss_last_guids = set(list(self._rss_last_guids)[2000:])

        text = _clean_rss_text(item)
        if not text:
            return False
        # Use the strict active-call signal (same as the X/twikit channel) so a
        # policy statement or retrospective report that merely *mentions*
        # distress vocabulary cannot become a live distress marker.
        distress = _is_actionable_rss_distress(text)
        # The RSS feeds are a news/archive channel, not an active-call channel.
        # Mark every row operator-only so the live edge never surfaces an NGO
        # article that merely mentions distress vocabulary, regardless of the
        # classifier outcome (publication_status == "private" is an explicit
        # opt-out in core/live_edge_publisher.py).
        # Context/news articles frequently mention courts, capitals, ports or
        # an NGO's headquarters. Those are subjects of the article, not the
        # boat's position. Gazetteer/relative inference is therefore enabled
        # only for a direct, actionable maritime call. News remains searchable
        # in the timeline but deliberately has no map geometry.
        numeric_coords = extract_numeric_coords(text) if distress else None
        relative_coords = (
            extract_relative_coords(text) if distress and not numeric_coords else None
        )
        coords = (
            numeric_coords
            or relative_coords
            or (extract_coords(text) if distress else None)
        )
        coordinate_source = (
            "post_text" if numeric_coords
            else "relative_place_offset" if relative_coords
            else "place_centroid" if coords
            else "none"
        )
        severity = classify_severity(text) if distress else "low"
        event = IntelEvent(
            # Stable across process restarts. Previously each scan generated
            # a random UUID, so the same RSS item could be inserted again.
            id=f"rss{dedup[:13]}",
            type="distress" if distress and severity in {"critical", "high"} else "news",
            severity=severity,
            lat=coords[0] if coords else None,
            lon=coords[1] if coords else None,
            title=item.get("title", "")[:200],
            text=text[:600],
            url=_best_url(item.get("link", ""), item.get("guid", "")),
            source=source,
            timestamp_utc=_parse_date(item.get("pub_date", "")),
            metadata={
                "source_policy": "official_rss",
                "transport": "rss",
                "is_distress": distress,
                "publication_status": "private",
                "report_kind": "distress" if distress else "news",
                "coordinate_source": coordinate_source,
                "location_policy": "operational_maritime_only",
                **({
                    "location_suppressed_reason": "non_operational_context",
                } if not distress else {}),
            },
        )
        added = intel_store.add(event, dedup_key=dedup)
        if added and event.type == "distress":
            from core.intel.triangulation import evaluate as evaluate_triangulation
            evaluate_triangulation(event)
        return added


def _clean_rss_text(item: dict[str, str]) -> str:
    """Return article text without markup or syndication boilerplate.

    WordPress descriptions often consist solely of "The post … appeared first
    on SOS MEDITERRANEE". Besides adding no article content, that footer used
    to trigger the bare ``SOS`` emergency marker.
    """
    title = str(item.get("title") or "")
    description = str(item.get("description") or "")
    description = re.sub(
        r"\bthe\s+post\b.{0,1200}?\bappeared\s+first\s+on\b.{0,160}?\.?\s*$",
        " ",
        description,
        flags=re.I | re.S,
    )
    description = re.sub(
        r"\bder\s+beitrag\b.{0,1200}?\berschien\s+zuerst\s+auf\b.{0,160}?\.?\s*$",
        " ",
        description,
        flags=re.I | re.S,
    )
    combined = f"{title} {description}"
    return re.sub(
        r"\s+",
        " ",
        html.unescape(re.sub(r"<[^>]+>", " ", combined)),
    ).strip()


def _is_actionable_rss_distress(text: str) -> bool:
    """Conservative operational gate for article-style RSS content.

    RSS summaries are retrospective far more often than social alert posts.
    A generic word such as ``shipwreck`` or ``missing`` is insufficient here:
    require present-tense operational evidence or an explicit emergency
    marker. The article is still retained as private news when this is false.
    """
    if not is_direct_distress_call(text):
        return False
    if _RSS_EMERGENCY_MARKER_RE.search(text):
        return True
    operational_patterns = (
        r"\b(?:we\s+(?:are|remain)|we['’]re)\s+in\s+contact\b",
        r"\b(?:we|relatives?|famil(?:y|ies))\s+(?:were|have\s+been)\s+alerted\b",
        r"\b(?:rescue|assistance|medical assistance)\s+(?:is\s+)?"
        r"(?:still\s+|urgently\s+|immediately\s+)?(?:needed|required|requested)\b",
        r"\b(?:urgent|ongoing|currently|right\s+now)\b.{0,100}"
        r"\b(?:distress|danger|at\s+risk|missing|rescue)\b",
        r"\b\d{1,3}\s+(?:people|persons|lives|passengers|migrants)\s+"
        r"(?:are\s+)?(?:in\s+distress|at\s+risk|in\s+danger|missing)\b",
    )
    return any(re.search(pattern, text, re.I) for pattern in operational_patterns)


def _safe_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
        return result if result != 0.0 else None
    except (TypeError, ValueError):
        return None


def _parse_date(raw: str) -> str:
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    try:
        return email.utils.parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _parse_rss(xml: str) -> list[dict[str, str]]:
    raw_items = re.findall(r"<item\b[^>]*>(.*?)</item>", xml, re.S | re.I)
    if not raw_items:
        raw_items = re.findall(r"<entry\b[^>]*>(.*?)</entry>", xml, re.S | re.I)
    return [
        {
            "title": _xml_tag(item, "title"),
            "description": _xml_tag(item, "description") or _xml_tag(item, "summary"),
            "link": _xml_tag(item, "link") or _xml_attr(item, "link", "href"),
            "guid": _xml_tag(item, "guid") or _xml_tag(item, "id"),
            "pub_date": _xml_tag(item, "pubDate")
            or _xml_tag(item, "published")
            or _xml_tag(item, "updated"),
        }
        for item in raw_items[:30]
    ]


def _xml_tag(xml: str, tag: str) -> str:
    match = re.search(
        rf"<{tag}\b[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>",
        xml,
        re.S | re.I,
    )
    return (match.group(1) or "").strip() if match else ""


def _xml_attr(xml: str, tag: str, attr: str) -> str:
    match = re.search(rf'<{tag}\b[^>]*{attr}="([^"]+)"', xml, re.I)
    return match.group(1).strip() if match else ""


def _best_url(link: str, guid: str) -> str:
    for candidate in (link, guid):
        if candidate.startswith(("https://", "http://")):
            return candidate
    return ""
