# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extract GPS coordinates from images via EXIF metadata or Claude Vision."""
from __future__ import annotations

import io
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_COORD_PATTERN = re.compile(
    r"""(?:lat(?:itude)?[\s:=]+)?
        (-?\d{1,2}(?:\.\d+)?)[°\s,]+
        (?:N|S)?\s*[,/\s]+\s*
        (-?\d{1,3}(?:\.\d+)?)[°\s,]+
        (?:E|W)?""",
    re.IGNORECASE | re.VERBOSE,
)


def _exif_gps(image_bytes: bytes) -> Optional[dict]:
    try:
        from PIL import Image
        from PIL.ExifTags import GPSTAGS, TAGS

        img = Image.open(io.BytesIO(image_bytes))
        raw = img._getexif() or {}
        exif: dict = {TAGS.get(k, k): v for k, v in raw.items()}
        gps_info = exif.get("GPSInfo") or {}
        gps: dict = {GPSTAGS.get(k, k): v for k, v in gps_info.items()}

        def _dms(dms, ref):
            d, m, s = (float(x) for x in dms)
            val = d + m / 60 + s / 3600
            return -val if ref in ("S", "W") else val

        if "GPSLatitude" in gps and "GPSLongitude" in gps:
            lat = _dms(gps["GPSLatitude"], gps.get("GPSLatitudeRef", "N"))
            lon = _dms(gps["GPSLongitude"], gps.get("GPSLongitudeRef", "E"))
            return {"lat": round(lat, 6), "lon": round(lon, 6), "method": "exif", "confidence": 1.0}
    except Exception as exc:
        logger.debug("EXIF extraction failed: %s", exc)
    return None


async def _vision_extract(image_bytes: bytes, mime: str = "image/jpeg") -> Optional[dict]:
    """Reserved hook for a future local open-source OCR/vision worker."""
    return None


async def extract_from_url(url: str) -> Optional[dict]:
    """Fetch image at URL and extract coordinates. Returns None if nothing found."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "SeaCommons/1.0"})
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            if not content_type.startswith("image/"):
                return None
            image_bytes = resp.content
    except Exception as exc:
        logger.warning("Failed to fetch image %s: %s", url, exc)
        return None

    # 1. EXIF — free, instant
    result = _exif_gps(image_bytes)
    if result:
        return result

    # 2. Claude Vision — costs ~$0.0001/image
    result = await _vision_extract(image_bytes, content_type)
    return result
