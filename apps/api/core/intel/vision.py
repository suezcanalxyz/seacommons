# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extract GPS coordinates from images via EXIF metadata or Claude Vision."""
from __future__ import annotations

import base64
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
    """Ask Claude Haiku to find coordinates in the image."""
    try:
        from anthropic import AsyncAnthropic

        b64 = base64.standard_b64encode(image_bytes).decode()
        client = AsyncAnthropic()
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": mime, "data": b64},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract any GPS coordinates, latitude/longitude values, or "
                            "place names with known coordinates from this image. "
                            "Reply ONLY with JSON: "
                            "{\"lat\": <float|null>, \"lon\": <float|null>, \"place\": \"<name or null>\", \"confidence\": <0-1>}. "
                            "If nothing found: {\"lat\": null, \"lon\": null, \"place\": null, \"confidence\": 0}."
                        ),
                    },
                ],
            }],
        )
        import json
        text = msg.content[0].text.strip()
        data = json.loads(text)
        if data.get("lat") is not None and data.get("lon") is not None:
            return {
                "lat": float(data["lat"]),
                "lon": float(data["lon"]),
                "place": data.get("place"),
                "method": "vision",
                "confidence": float(data.get("confidence", 0.7)),
            }
        if data.get("place"):
            return {"lat": None, "lon": None, "place": data["place"], "method": "vision", "confidence": 0.3}
    except Exception as exc:
        logger.warning("Claude Vision extraction failed: %s", exc)
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
