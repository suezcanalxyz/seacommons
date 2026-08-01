#!/usr/bin/env python3
"""Re-run bounded OCR for persisted Alarm Phone screenshots."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db.models import IntelEventDB
from core.db.session import session_scope
from core.intel.alarm_phone_monitor import _ocr_photo, _x_photo_urls
from core.intel.geoextract import extract_numeric_coords, extract_relative_coords


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tweet-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    wanted = set(args.tweet_id)
    results: list[dict] = []
    with session_scope() as db:
        rows = (
            db.query(IntelEventDB)
            .filter(IntelEventDB.source == "Alarm Phone")
            .order_by(IntelEventDB.timestamp_utc.desc())
            .limit(max(1, min(args.limit, 500)))
            .all()
        )
        for row in rows:
            metadata = dict(row.meta or {})
            tweet_id = str(metadata.get("tweet_id") or "")
            if not tweet_id or (wanted and tweet_id not in wanted):
                continue
            numeric_coordinate = extract_numeric_coords(row.text or "")
            relative_coordinate = extract_relative_coords(row.text or "")
            coordinate = numeric_coordinate or relative_coordinate
            coordinate_source = (
                "post_text"
                if numeric_coordinate
                else "relative_place_offset"
                if relative_coordinate
                else "media_ocr_text"
            )
            photos: list[str] = []
            matched_url = ""
            if coordinate is None:
                photos = _x_photo_urls(tweet_id)
                for photo_url in photos:
                    coordinate, _ = _ocr_photo(photo_url)
                    if coordinate is not None:
                        matched_url = photo_url
                        break
            result = {
                "event_id": row.id,
                "tweet_id": tweet_id,
                "photos": len(photos),
                "coordinate": coordinate,
                "coordinate_source": coordinate_source if coordinate else "none",
                "applied": bool(args.apply and coordinate),
            }
            results.append(result)
            if args.apply and coordinate:
                row.lat, row.lon = coordinate
                metadata.update({
                    "coordinate_source": coordinate_source,
                    "coordinate_review_status": (
                        "machine_ocr_unverified"
                        if coordinate_source == "media_ocr_text"
                        else "source_text"
                    ),
                    "location_uncertainty_m": {
                        "post_text": 250,
                        "media_ocr_text": 1500,
                        "relative_place_offset": 15_000,
                    }[coordinate_source],
                    "ocr_attempted": coordinate_source == "media_ocr_text",
                    "ocr_backfilled_at": datetime.now(timezone.utc).isoformat(),
                })
                if matched_url:
                    metadata["ocr_media_url"] = matched_url
                row.meta = metadata
        db.flush()
    print(json.dumps(results, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
