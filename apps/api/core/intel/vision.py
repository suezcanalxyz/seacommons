# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extract GPS coordinates from images via EXIF metadata or Claude Vision."""
from __future__ import annotations

import io
import logging
import re
from typing import Optional

from core.net.outbound import async_request
from core.net.policy import IMAGE, OutboundError, TrustProfile

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
        raw = img._getexif() or {}  # type: ignore[attr-defined]
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
    """Fetch an untrusted public image and extract coordinates."""
    try:
        response = await async_request(
            url,
            profile=TrustProfile.PUBLIC_UNTRUSTED,
            contract=IMAGE,
            headers={"User-Agent": "SeaCommons/1.0"},
            timeout=15.0,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        image_bytes = response.body
    except OutboundError as exc:
        logger.warning("Failed to fetch image: outbound=%s", exc.code)
        return None

    # 1. EXIF — free, instant
    result = _exif_gps(image_bytes)
    if result:
        return result

    # 2. Claude Vision — costs ~$0.0001/image
    result = await _vision_extract(image_bytes, content_type)
    return result
