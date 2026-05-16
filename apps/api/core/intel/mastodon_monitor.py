# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Mastodon public timeline monitor for maritime NGO accounts.

Uses the public Mastodon REST API — no authentication required for public accounts.
Polls a curated list of NGO handles across multiple Mastodon instances.

API endpoint: https://{instance}/api/v1/accounts/{id}/statuses (public, no auth)
Account lookup: https://{instance}/api/v1/accounts/lookup?acct={handle}

Runs in a background daemon thread; events are pushed to IntelStore.
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

_POLL_INTERVAL_S = 5 * 60   # 5 minutes per account cycle
_HEADERS = {
    "User-Agent": "SeacommonsIntel/1.0 (open-source SAR dashboard)",
    "Accept": "application/json",
}

# Known NGO accounts on Mastodon — (instance, handle_without_at, label)
# Public-facing accounts; verified by checking their profiles.
_NGO_ACCOUNTS = [
    ("mastodon.social",       "alarm_phone",        "Alarm Phone"),
    ("mastodon.social",       "sosmediterranee",     "SOS Méditerranée"),
    ("social.coop",           "seawatch",           "Sea Watch"),
    ("mastodon.social",       "MSF_Sea",            "MSF Sea"),
    ("mastodon.social",       "InfoMigrants",       "InfoMigrants"),
    ("journa.host",           "WatchTheMed",        "Watch The Med"),
]

# Mediterranean distress keywords for relevance filtering
_MED_KW = frozenset([
    "mediterranean", "lampedusa", "sicily", "libya", "tunisia", "malta",
    "migrant", "migrants", "refugee", "distress", "rescue", "naufragio",
    "naufrage", "méditerranée", "aegean", "drowning", "shipwreck", "sar",
    "seenotrettung", "sauvetage", "detention", "alarm", "crossing",
])


class MastodonMonitor:
    """
    Polls public Mastodon accounts for maritime distress posts.
    Falls back silently if an account is not found on a given instance.
    """

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # account name → max_id for incremental polling
        self._account_ids: dict[str, Optional[str]] = {}   # cache: key → numeric account id
        self._seen: set[str] = set()
        self._seen_lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="intel-mastodon"
        )
        self._thread.start()
        logger.info("MastodonMonitor started (%d accounts)", len(_NGO_ACCOUNTS))

    def stop(self) -> None:
        self._running = False

    # ── Main loop ──────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        from core.intel.source_registry import source_registry
        source_registry.register("Mastodon", "mastodon")

        while self._running:
            new_total = 0
            error_str: Optional[str] = None
            for instance, handle, label in _NGO_ACCOUNTS:
                if not self._running:
                    break
                try:
                    account_id = self._resolve_account(instance, handle)
                    if not account_id:
                        continue
                    statuses = self._fetch_statuses(instance, account_id)
                    for status in statuses:
                        if self._ingest(status, label, instance):
                            new_total += 1
                except Exception as exc:
                    logger.debug("Mastodon @%s@%s error: %s", handle, instance, exc)
                    error_str = str(exc)
                # brief pause between accounts to avoid hammering instances
                time.sleep(4)

            source_registry.record_poll("Mastodon", events_found=new_total, error=error_str)
            if new_total:
                logger.info("Mastodon: +%d new intel events", new_total)
            time.sleep(_POLL_INTERVAL_S)

    # ── Account resolution ─────────────────────────────────────────────────────

    def _resolve_account(self, instance: str, handle: str) -> Optional[str]:
        """Lookup the numeric account ID for a handle on a given instance."""
        cache_key = f"{handle}@{instance}"
        cached = self._account_ids.get(cache_key)
        if cached:
            return cached

        url = f"https://{instance}/api/v1/accounts/lookup?acct={urllib.parse.quote(handle)}"
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            account_id = str(data["id"])
            self._account_ids[cache_key] = account_id
            return account_id
        except Exception as exc:
            logger.debug("Mastodon lookup %s@%s failed: %s", handle, instance, exc)
            self._account_ids[cache_key] = None  # cache the miss
            return None

    # ── Status fetch ────────────────────────────────────────────────────────────

    def _fetch_statuses(self, instance: str, account_id: str) -> list[dict[str, Any]]:
        """Fetch recent public statuses for an account (up to 20)."""
        url = f"https://{instance}/api/v1/accounts/{account_id}/statuses?limit=20&exclude_replies=true"
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read())

    # ── Ingestion ──────────────────────────────────────────────────────────────

    def _ingest(self, status: dict[str, Any], source_label: str, instance: str) -> bool:
        status_id = str(status.get("id", ""))
        dedup = hashlib.sha1(f"mastodon:{instance}:{status_id}".encode()).hexdigest()[:16]

        with self._seen_lock:
            if dedup in self._seen:
                return False
            self._seen.add(dedup)
            if len(self._seen) > 3000:
                self._seen = set(list(self._seen)[1500:])

        # Strip HTML tags from content
        raw_content = status.get("content", "")
        text = re.sub(r"<[^>]+>", " ", raw_content)
        text = re.sub(r"\s+", " ", text).strip()
        # Decode HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")

        if not text or len(text) < 15:
            return False

        # Relevance filter: must mention Med/distress keywords
        tl = text.lower()
        if not any(kw in tl for kw in _MED_KW) and not is_distress(text):
            return False

        coords = extract_coords(text)
        severity = classify_severity(text)

        # Extract media attachment image URLs for potential Vision fallback
        media_urls = [
            att.get("url", "")
            for att in (status.get("media_attachments") or [])
            if att.get("type") == "image" and att.get("url")
        ]

        # If no coords from text, try Vision on first image
        if coords is None and media_urls:
            vision = _vision_extract_sync(media_urls[0])
            if vision:
                coords = (vision["lat"], vision["lon"])
                logger.info("Mastodon Vision coords from %s: %s", source_label, coords)

        account = status.get("account", {})
        author = account.get("username", "")
        url_val = status.get("url", "")

        created_at_raw = status.get("created_at", "")
        ts = _parse_mastodon_date(created_at_raw)

        title_text = text[:120].rstrip()
        title = f"@{author} ({source_label}): {title_text}{'…' if len(text) > 120 else ''}"

        event_type = "distress" if severity in ("critical", "high") and is_distress(text) else "mastodon"

        event = IntelEvent(
            type=event_type,
            severity=severity,
            lat=coords[0] if coords else None,
            lon=coords[1] if coords else None,
            title=title,
            text=text[:600],
            url=url_val,
            source=source_label,
            author=author,
            timestamp_utc=ts,
            metadata={
                "platform": "mastodon",
                "instance": instance,
                "status_id": status_id,
                "media_urls": media_urls[:3],
            },
        )
        return intel_store.add(event, dedup_key=dedup)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_mastodon_date(raw: str) -> str:
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(raw[:len(fmt) + 6], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return datetime.now(timezone.utc).isoformat()


def _vision_extract_sync(img_url: str) -> Optional[dict[str, Any]]:
    try:
        import asyncio
        from core.intel.vision import extract_from_url
        return asyncio.run(extract_from_url(img_url))
    except Exception as exc:
        logger.debug("Vision extract failed for %s: %s", img_url, exc)
        return None
