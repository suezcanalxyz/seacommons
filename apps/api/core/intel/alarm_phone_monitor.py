# SPDX-License-Identifier: AGPL-3.0-or-later
"""Collect Alarm Phone's public X timeline from its first-party website.

Alarm Phone republishes its X posts in the server-rendered HTML at
alarmphone.org. This narrow collector reads that official public copy without
an X login, account automation, or an unofficial social-media mirror.
"""
from __future__ import annotations

import html
import io
import json
import logging
import math
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from core.intel.geoextract import (
    classify_severity,
    extract_coords,
    extract_numeric_coords,
    extract_relative_coords,
    is_direct_distress_call,
    is_resolved_distress,
)
from core.intel.store import IntelEvent, intel_store
from core.config import config

logger = logging.getLogger(__name__)

SOURCE_NAME = "Alarm Phone / X official site"
PAGE_URL = "https://alarmphone.org/en/"
_SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
_X_EPOCH_MS = 1_288_834_974_657
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_ALLOWED_MEDIA_HOSTS = frozenset({"pbs.twimg.com"})
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


def parse_official_timeline(document: str) -> list[dict[str, Any]]:
    """Extract post IDs and text from Alarm Phone's server-rendered timeline."""
    posts: list[dict[str, Any]] = []
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


def _x_syndication(tweet_id: str) -> dict[str, Any]:
    """Fetch X's public embed syndication response for one tweet (free, no key)."""
    request = urllib.request.Request(
        f"{_SYNDICATION_URL}?id={tweet_id}&lang=en&token=1",
        headers={**_HEADERS, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def _x_photo_urls(payload: dict[str, Any]) -> list[str]:
    """Extract public photo URLs from an already-fetched syndication payload."""
    urls: list[str] = []
    for photo in payload.get("photos") or []:
        url = str(photo.get("url") or "")
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.hostname in _ALLOWED_MEDIA_HOSTS:
            urls.append(url)
    return urls[:4]


def consensus_ocr_coordinate(texts: list[str]) -> Optional[tuple[float, float]]:
    """Accept an OCR location only when two independent layout passes agree."""
    candidates = [
        candidate
        for text in texts
        if (candidate := extract_numeric_coords(text)) is not None
    ]
    for index, first in enumerate(candidates):
        for second in candidates[index + 1 :]:
            if abs(first[0] - second[0]) <= 0.01 and abs(first[1] - second[1]) <= 0.01:
                return (
                    round((first[0] + second[0]) / 2, 5),
                    round((first[1] + second[1]) / 2, 5),
                )
    return None


def ocr_png_coordinate(
    processed_png: bytes,
    *,
    executable: Optional[str] = None,
) -> tuple[Optional[tuple[float, float]], bool]:
    """Run independent Tesseract layouts over an already-normalised PNG."""
    command = executable or shutil.which("tesseract")
    if not command:
        return None, False
    texts: list[str] = []
    for page_mode in ("3", "6", "11"):
        try:
            result = subprocess.run(
                [command, "stdin", "stdout", "--psm", page_mode, "-l", "eng"],
                input=processed_png,
                capture_output=True,
                check=False,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            texts.append(result.stdout.decode("utf-8", errors="replace")[:20_000])
    consensus = consensus_ocr_coordinate(texts)
    if consensus is not None:
        return consensus, True
    # A tightly cropped popup may be legible in only one Tesseract layout.
    # Accept it as explicitly unverified only when exactly one valid,
    # hemisphere-labelled coordinate survives the strict range parser.
    candidates = {
        candidate for text in texts
        if (candidate := extract_numeric_coords(text)) is not None
    }
    return (next(iter(candidates)) if len(candidates) == 1 else None), True


def _ocr_photo(url: str) -> tuple[Optional[tuple[float, float]], bool]:
    """Download one bounded public image and run three local Tesseract passes."""
    executable = shutil.which("tesseract")
    if not executable:
        return None, False
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_MEDIA_HOSTS:
        return None, False

    request = urllib.request.Request(
        url,
        headers={**_HEADERS, "Accept": "image/jpeg,image/png,image/webp"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        content_type = str(response.headers.get("Content-Type") or "").lower()
        if not content_type.startswith("image/"):
            return None, False
        payload = response.read(_MAX_IMAGE_BYTES + 1)
    if len(payload) > _MAX_IMAGE_BYTES:
        return None, False

    from PIL import Image, ImageFilter, ImageOps

    Image.MAX_IMAGE_PIXELS = 25_000_000
    attempted = False
    with Image.open(io.BytesIO(payload)) as source:
        image = ImageOps.exif_transpose(source).convert("L")
        width, height = image.size
        popup_boxes: list[tuple[int, int, int, int]] = []
        try:
            import numpy as np

            pixels = np.asarray(image)
            bright = pixels >= 235
            active_rows = np.flatnonzero(
                bright.sum(axis=1) >= max(80, int(width * 0.22))
            )

            def runs(values):
                if not len(values):
                    return []
                output = []
                start = previous = int(values[0])
                for raw in values[1:]:
                    value = int(raw)
                    if value != previous + 1:
                        output.append((start, previous + 1))
                        start = value
                    previous = value
                output.append((start, previous + 1))
                return output

            row_runs = runs(active_rows)
            merged_rows: list[tuple[int, int]] = []
            for top, bottom in row_runs:
                if merged_rows and top - merged_rows[-1][1] <= 32:
                    merged_rows[-1] = (merged_rows[-1][0], bottom)
                else:
                    merged_rows.append((top, bottom))

            for top, bottom in merged_rows:
                if bottom - top < 30:
                    continue
                active_columns = np.flatnonzero(
                    bright[top:bottom].sum(axis=0)
                    >= max(15, int((bottom - top) * 0.42))
                )
                for left, right in runs(active_columns):
                    if right - left < 140:
                        continue
                    padding = 12
                    popup_boxes.append((
                        max(0, left - padding),
                        max(0, top - padding),
                        min(width, right + padding),
                        min(height, bottom + padding),
                    ))
        except Exception:
            popup_boxes = []
        # Alarm Phone map popups can appear at the top, centre or bottom. A
        # full-map OCR pass often misses their small coordinate row, so scan
        # three overlapping horizontal bands as well as the complete image.
        boxes = popup_boxes + [
            (0, 0, width, height),
            (0, 0, width, max(1, int(height * 0.55))),
            (0, int(height * 0.22), width, max(1, int(height * 0.78))),
            (0, int(height * 0.45), width, height),
        ]
        for box in boxes:
            candidate_image = image.crop(box)
            scale = min(4, max(1, math.ceil(2400 / max(1, candidate_image.width))))
            if scale > 1:
                candidate_image = candidate_image.resize(
                    (candidate_image.width * scale, candidate_image.height * scale),
                    Image.Resampling.LANCZOS,
                )
            candidate_image = ImageOps.autocontrast(candidate_image).filter(ImageFilter.SHARPEN)
            output = io.BytesIO()
            candidate_image.save(output, format="PNG", optimize=True)
            coordinate, did_attempt = ocr_png_coordinate(
                output.getvalue(), executable=executable
            )
            attempted = attempted or did_attempt
            if coordinate is not None:
                return coordinate, attempted
    return None, attempted


class AlarmPhoneMonitor:
    """Continuously collect public Alarm Phone posts from alarmphone.org."""

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._media_cache: dict[str, tuple[Optional[tuple[float, float]], int, bool]] = {}

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
                text_coordinate = (
                    extract_numeric_coords(post.get("text", ""))
                    or extract_relative_coords(post.get("text", ""))
                )
                if text_coordinate is not None:
                    # Text/declared offsets are available immediately; do not
                    # delay ingestion behind several expensive OCR passes.
                    media_coords, media_count, ocr_attempted, reply_count = None, 0, False, 0
                else:
                    media_coords, media_count, ocr_attempted, reply_count = self._media_context(post["id"])
                post["media_coords"] = media_coords
                post["media_count"] = media_count
                post["ocr_attempted"] = ocr_attempted
                post["reply_count"] = reply_count
                if self._ingest(post):
                    new_count += 1
        except Exception as exc:
            error = str(exc)
            logger.warning("Alarm Phone official timeline error: %s", exc)
        source_registry.record_poll(SOURCE_NAME, events_found=new_count, error=error)

    def _loop(self) -> None:
        while self._running:
            self.scan()
            poll_interval = max(30, int(config.ALARM_PHONE_POLL_INTERVAL_S))
            for _ in range(poll_interval):
                if not self._running:
                    return
                time.sleep(1)

    def _media_context(
        self,
        tweet_id: str,
    ) -> tuple[Optional[tuple[float, float]], int, bool, int]:
        cached = self._media_cache.get(tweet_id)
        if cached is not None:
            return cached
        try:
            payload = _x_syndication(tweet_id)
            photos = _x_photo_urls(payload)
            reply_count = int(payload.get("conversation_count") or 0)
        except Exception as exc:
            logger.debug("Alarm Phone media lookup failed for %s: %s", tweet_id, exc)
            return None, 0, False, 0
        coordinate: Optional[tuple[float, float]] = None
        attempted = False
        for photo_url in photos:
            try:
                candidate, did_attempt = _ocr_photo(photo_url)
                attempted = attempted or did_attempt
                if candidate is not None:
                    coordinate = candidate
                    break
            except Exception as exc:
                attempted = True
                logger.debug("Alarm Phone media OCR failed for %s: %s", tweet_id, exc)
        result = (coordinate, len(photos), attempted, reply_count)
        self._media_cache[tweet_id] = result
        return result

    def _ingest(self, post: dict[str, Any]) -> bool:
        text = post.get("text", "")
        tweet_id = post.get("id", "")
        if len(text) < 10 or not tweet_id:
            return False
        distress = is_direct_distress_call(text)
        text_coords = extract_numeric_coords(text)
        media_coords = post.get("media_coords")
        relative_coords = extract_relative_coords(text)
        coords = text_coords or media_coords or relative_coords or extract_coords(text)
        if text_coords:
            coordinate_source = "post_text"
            location_uncertainty_m = 250
        elif media_coords:
            coordinate_source = "media_ocr_text"
            location_uncertainty_m = 1500
        elif relative_coords:
            coordinate_source = "relative_place_offset"
            location_uncertainty_m = 15_000
        elif coords:
            coordinate_source = "place_centroid"
            location_uncertainty_m = 25_000
        else:
            coordinate_source = "none"
            location_uncertainty_m = None
        snippet = re.sub(r"https?://\S+", "", text).strip()
        observed_at = datetime.now(timezone.utc).isoformat()
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
                "media_transport": (
                    "x_embed_syndication"
                    if int(post.get("media_count") or 0) > 0
                    else "none"
                ),
                "is_distress": distress,
                "distress_classification": (
                    "direct_call" if distress else "context"
                ),
                "verification_status": (
                    "machine_extracted_unverified"
                    if coordinate_source.startswith("media_ocr")
                    else "unverified_public_source"
                ),
                "coordinate_source": coordinate_source,
                "coordinate_review_status": (
                    "machine_ocr_unverified"
                    if coordinate_source.startswith("media_ocr")
                    else "not_required"
                ),
                "location_uncertainty_m": location_uncertainty_m,
                "media_count": int(post.get("media_count") or 0),
                "ocr_attempted": bool(post.get("ocr_attempted")),
                # Free (syndication conversation_count), but only a count — the
                # reply text itself needs the paid X API or the tweet's own web
                # page, so we link out rather than fabricate reply content.
                "reply_count": int(post.get("reply_count") or 0),
                "incident_status": "resolved" if is_resolved_distress(text) else "active" if distress else "context",
                "first_source_seen_at": observed_at,
                "last_source_seen_at": observed_at,
                "source_scan_count": 1,
            },
        )
        added = intel_store.add(event, dedup_key=f"x:{tweet_id}")
        if not added and coords:
            location_metadata = {
                key: value
                for key, value in event.metadata.items()
                if key not in {
                    "first_source_seen_at", "last_source_seen_at", "source_scan_count"
                }
            }
            intel_store.enrich_location(
                event.id,
                lat=coords[0],
                lon=coords[1],
                metadata=location_metadata,
            )
        if not added:
            intel_store.touch_source_observation(event.id, observed_at)
        if added and distress:
            from core.intel.triangulation import evaluate as evaluate_triangulation
            evaluate_triangulation(event)
        stored_event = intel_store.get(event.id) or event
        if (
            distress
            and config.INTEL_AUTO_DRIFT_ENABLED
            and stored_event.lat is not None
            and stored_event.lon is not None
            and stored_event.metadata.get("coordinate_source")
            in {"post_text", "media_ocr_consensus", "media_ocr_text", "relative_place_offset"}
            and stored_event.metadata.get("drift_status") not in {"computing", "completed"}
        ):
            try:
                from core.api.routes.intel import schedule_intel_drift
                schedule_intel_drift(
                    stored_event.id,
                    stored_event.lat,
                    stored_event.lon,
                    persons=None,
                    vessel_type="rubber_boat",
                    observed_at=stored_event.timestamp_utc,
                )
            except Exception as exc:
                logger.debug("Alarm Phone auto-drift deferred for %s: %s", event.id, exc)
        return added
