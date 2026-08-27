# SPDX-License-Identifier: AGPL-3.0-or-later
"""Re-process historical Alarm Phone events with the current coordinate
pipeline.

Many past events -- including archived ones -- carry only a region-area or
place-centroid position (or none), even though the tweet included a map
screenshot with the real coordinates. The OCR and pin-from-landmarks
improvements only apply to new ingestion; this walks the stored events,
re-fetches the tweet images from the public syndication CDN (no account),
runs the current extraction, and writes back a real position. Optionally it
then queues a drift for the event's own moment.

Dry-run by default:

    python -m core.intel.backfill_alarm_phone            # report only
    python -m core.intel.backfill_alarm_phone --apply
    python -m core.intel.backfill_alarm_phone --apply --drift --limit 50
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Positions we are willing to replace with an image-derived one.
_WEAK_COORD_SOURCES = frozenset({
    "", "none", "None", "region_area", "place_centroid",
})
_ALARM_PHONE_HANDLES = frozenset({"alarm_phone", "alarmphone"})


def _is_alarm_phone(row: Any) -> bool:
    source = str(getattr(row, "source", "") or "").lower()
    if source in _ALARM_PHONE_HANDLES:
        return True
    meta = getattr(row, "meta", None) or {}
    return str(meta.get("tracked_account") or "").lower() in _ALARM_PHONE_HANDLES


def _is_weak_position(row: Any) -> bool:
    meta = getattr(row, "meta", None) or {}
    if getattr(row, "lat", None) is None or getattr(row, "lon", None) is None:
        return True
    return str(meta.get("coordinate_source") or "") in _WEAK_COORD_SOURCES


def find_candidates(limit: int = 200) -> list[Any]:
    from sqlalchemy import select

    from core.db.models import IntelEventDB
    from core.db.session import session_scope

    with session_scope() as db:
        rows = db.execute(
            select(IntelEventDB).order_by(IntelEventDB.timestamp_utc.desc()).limit(limit * 4)
        ).scalars().all()
        # detach a plain snapshot so we can work outside the session
        out = []
        for row in rows:
            if not _is_alarm_phone(row) or not _is_weak_position(row):
                continue
            meta = dict(row.meta or {})
            out.append({
                "id": row.id,
                "tweet_id": str(meta.get("tweet_id") or ""),
                "quoted_tweet_id": str(meta.get("quoted_tweet_id") or ""),
                "media_urls": list(meta.get("media_urls") or []),
                "coordinate_source": meta.get("coordinate_source"),
                "timestamp_utc": row.timestamp_utc,
                "title": (row.title or "")[:80],
                "lifecycle": meta.get("incident_lifecycle"),
                "persons": meta.get("persons"),
                "vessel_type": meta.get("vessel_type"),
            })
            if len(out) >= limit:
                break
    return out


def resolve_position(candidate: dict) -> tuple[float, float, str] | None:
    """Best image-derived coordinate for one candidate, or None."""
    from core.intel.x_media_utils import _ocr_photo, fetch_tweet_photos

    urls = list(candidate.get("media_urls") or [])
    for tweet_id in (candidate.get("tweet_id"), candidate.get("quoted_tweet_id")):
        if tweet_id and not urls:
            urls = fetch_tweet_photos(tweet_id)
        elif tweet_id:
            urls += [u for u in fetch_tweet_photos(tweet_id) if u not in urls]

    for url in urls[:6]:
        try:
            coord, _attempted, method = _ocr_photo(url)
        except Exception as exc:
            logger.debug("backfill OCR failed for %s: %s", url, exc)
            continue
        if coord is not None:
            return coord[0], coord[1], method
    return None


def apply_position(event_id: str, lat: float, lon: float, method: str) -> bool:
    from core.db.models import IntelEventDB
    from core.db.session import session_scope

    uncertainty = 1500 if method == "text" else 4000
    with session_scope() as db:
        row = db.query(IntelEventDB).filter(IntelEventDB.id == event_id).first()
        if row is None:
            return False
        merged = dict(row.meta or {})
        merged.update({
            "coordinate_source": f"media_{'ocr_text' if method == 'text' else 'pin_landmark'}_backfill",
            "coordinate_review_status": "machine_ocr_unverified",
            "verification_status": "machine_extracted_unverified",
            "location_uncertainty_m": uncertainty,
            "backfilled_at": datetime.now(timezone.utc).isoformat(),
        })
        # a real point supersedes any stale search polygon
        for key in ("area_geojson", "area_confidence", "area_weather_narrowed"):
            merged.pop(key, None)
        row.lat = float(lat)
        row.lon = float(lon)
        row.meta = merged
        db.flush()
    return True


def run(*, apply: bool, limit: int, with_drift: bool) -> dict:
    candidates = find_candidates(limit)
    resolved = 0
    drifted = 0
    for candidate in candidates:
        position = resolve_position(candidate)
        status = "no-image-coordinate"
        if position is not None:
            lat, lon, method = position
            status = f"{lat:.5f},{lon:.5f} via {method}"
            resolved += 1
            if apply and apply_position(candidate["id"], lat, lon, method):
                status += " [applied]"
                if with_drift:
                    try:
                        from core.intel.drift_service import schedule_intel_drift

                        if schedule_intel_drift(
                            candidate["id"], lat, lon,
                            candidate.get("persons"), candidate.get("vessel_type") or "rubber_boat",
                            candidate.get("timestamp_utc") or datetime.now(timezone.utc).isoformat(),
                            force=True,
                        ):
                            drifted += 1
                            status += " [drift queued]"
                    except Exception as exc:
                        logger.warning("backfill drift failed for %s: %s", candidate["id"], exc)
        logger.info(
            "%-14s %s  %s  -> %s",
            candidate["id"][:14], candidate["timestamp_utc"], candidate["title"], status,
        )
    return {
        "candidates": len(candidates),
        "resolved": resolved,
        "applied": resolved if apply else 0,
        "drifts_queued": drifted,
        "dry_run": not apply,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write positions back (default: dry run)")
    parser.add_argument("--drift", action="store_true", help="queue a drift for each backfilled event")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    from core.db.session import init_database

    init_database()
    summary = run(apply=args.apply, limit=args.limit, with_drift=args.drift)
    logger.info("---")
    for key, value in summary.items():
        logger.info("%-16s %s", key, value)


if __name__ == "__main__":
    main()
