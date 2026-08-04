# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared X/Twitter media utilities: Snowflake ID decoding and image OCR.

Split out of the old alarm_phone_monitor.py (the first-party alarmphone.org
site scraper, removed once twikit became the sole, stable X source) because
twikit_monitor.py's own image-based coordinate extraction depends on the OCR
pipeline here — these functions are source-agnostic, not specific to any one
collector.
"""
from __future__ import annotations

import io
import math
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from core.intel.geoextract import extract_numeric_coords

_X_EPOCH_MS = 1_288_834_974_657
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_ALLOWED_MEDIA_HOSTS = frozenset({"pbs.twimg.com"})
_HEADERS = {
    "User-Agent": "SeaCommonsIntel/2.0 (+https://seacommons.org)",
    "Accept": "text/html,application/xhtml+xml",
}


def x_id_timestamp(tweet_id: str) -> str:
    """Recover the exact UTC creation time encoded in an X Snowflake ID."""
    milliseconds = (int(tweet_id) >> 22) + _X_EPOCH_MS
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).isoformat()


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
