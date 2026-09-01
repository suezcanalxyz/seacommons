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
                "text": (row.text or "")[:500],
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
            result = _ocr_photo(url)
        except Exception as exc:
            logger.debug("backfill OCR failed for %s: %s", url, exc)
            continue
        coord, method = result[0], result[2]
        if coord is not None:
            return coord[0], coord[1], method
    return None


def _outcome_for_method(method: str) -> str:
    """Map the OCR method to a Phase-5 report bucket."""
    from core.intel.location_evidence import evidence_from_ocr_method

    evidence = evidence_from_ocr_method(method, None, None)
    review = evidence.review_status
    if "disputed" in review:
        return "disputed"
    if evidence.coordinate_source == "media_ocr_consensus":
        return "newly_positioned_exact"
    return "newly_positioned_approximate"


def _is_land_case(candidate: dict) -> bool:
    from core.intel.humanitarian import _case_type

    title = candidate.get("title") or ""
    return _case_type(title, distress=False, resolved=False) == "land_humanitarian"


def _lifecycle_would_change(candidate: dict) -> bool:
    from core.intel import lifecycle
    from core.intel.store import IntelEvent

    stored = str(candidate.get("lifecycle") or "").lower()
    if not stored:
        return False
    probe = IntelEvent(
        id=str(candidate["id"]),
        type="twitter",
        title=candidate.get("title") or "",
        text=candidate.get("text") or "",
        timestamp_utc=candidate.get("timestamp_utc") or "",
    )
    recomputed = lifecycle.distress_lifecycle(
        probe, now=datetime.now(timezone.utc), same_source=[]
    )
    return recomputed != stored


def apply_position(event_id: str, lat: float, lon: float, method: str) -> str:
    """Write an image-derived position back, unless it would downgrade the
    stored evidence. Idempotent: a re-run of an already-backfilled row is a
    no-op. Returns a Phase-5 outcome bucket.
    """
    from core.db.models import IntelEventDB
    from core.db.session import session_scope
    from core.intel.landmask import in_operational_region, nearest_sea_point
    from core.intel.location_evidence import evidence_from_ocr_method, metadata_quality

    if not in_operational_region(lat, lon):
        logger.info("backfill: %s coordinate %.4f,%.4f out of region — skipped", event_id, lat, lon)
        return "still_unpositioned"
    lat, lon = nearest_sea_point(float(lat), float(lon))
    evidence = evidence_from_ocr_method(method, lat, lon)
    new_meta = evidence.as_metadata()

    with session_scope() as db:
        row = db.query(IntelEventDB).filter(IntelEventDB.id == event_id).first()
        if row is None:
            return "still_unpositioned"
        existing = dict(row.meta or {})
        # Never downgrade higher-quality evidence (F-04); a re-run over an
        # equal-or-better position is a no-op.
        if row.lat is not None and metadata_quality(new_meta) <= metadata_quality(existing):
            return "already_good"
        merged = {
            **existing,
            **new_meta,
            "backfilled_at": datetime.now(timezone.utc).isoformat(),
        }
        for key in ("area_geojson", "area_confidence", "area_weather_narrowed"):
            merged.pop(key, None)
        row.lat = float(lat)
        row.lon = float(lon)
        row.meta = merged
        row.coordinate_review_status = new_meta.get("coordinate_review_status")
        row.location_uncertainty_m = new_meta.get("location_uncertainty_m")
        db.flush()
    return _outcome_for_method(method)


def _backfill_drift_eligible(candidate: dict, lat: float, lon: float, method: str) -> bool:
    """Whether a backfilled position may seed a drift (docs/fixes.md F-01/F-05).

    Live ingestion and backfill must share one drift eligibility policy. A
    backfilled image-derived coordinate is always ``machine_ocr_unverified``,
    so this currently rejects every backfill drift -- exactly the freeze F-05
    calls for until the shared LocationEvidence work (Phase 1) lands.
    """
    from core.intel.drift_service import is_auto_drift_eligible
    from core.intel.location_evidence import evidence_from_ocr_method
    from core.intel.store import IntelEvent

    probe = IntelEvent(
        id=str(candidate["id"]),
        type="twitter",
        lat=lat,
        lon=lon,
        metadata={
            "is_distress": True,
            "incident_lifecycle": candidate.get("lifecycle") or "active",
            **evidence_from_ocr_method(method, lat, lon).as_metadata(),
        },
    )
    eligible, _reason = is_auto_drift_eligible(probe)
    return eligible


_REPORT_KEYS = (
    "scanned",
    "already_good",
    "newly_positioned_exact",
    "newly_positioned_approximate",
    "region_only",
    "still_unpositioned",
    "disputed",
    "land_humanitarian",
    "lifecycle_changed",
    "duplicate_merged",
    "drift_eligible",
    "drift_rejected",
)
# Buckets that mean "a position was written" (or would be, in a dry run).
_APPLIED_OUTCOMES = frozenset(
    {"newly_positioned_exact", "newly_positioned_approximate", "disputed"}
)


def run(*, apply: bool, limit: int, with_drift: bool) -> dict:
    """docs/fixes.md Phase 5: idempotent, never-downgrade reprocessing with a
    full outcome report. Run dry (default), audit, then --apply, audit again,
    then optionally --drift (only events passing is_auto_drift_eligible)."""
    candidates = find_candidates(limit)
    report = {key: 0 for key in _REPORT_KEYS}
    report["scanned"] = len(candidates)

    for candidate in candidates:
        if _lifecycle_would_change(candidate):
            report["lifecycle_changed"] += 1

        if _is_land_case(candidate):
            report["land_humanitarian"] += 1
            _log(candidate, "land humanitarian -> no maritime position")
            continue

        position = resolve_position(candidate)
        if position is None:
            bucket = (
                "region_only"
                if str(candidate.get("coordinate_source") or "") == "region_area"
                else "still_unpositioned"
            )
            report[bucket] += 1
            _log(candidate, f"no image coordinate -> {bucket}")
            continue

        lat, lon, method = position
        if apply:
            outcome = apply_position(candidate["id"], lat, lon, method)
        else:
            from core.intel.landmask import in_operational_region

            outcome = _outcome_for_method(method) if in_operational_region(lat, lon) else "still_unpositioned"
        report[outcome] = report.get(outcome, 0) + 1

        if outcome in _APPLIED_OUTCOMES:
            if _backfill_drift_eligible(candidate, lat, lon, method):
                report["drift_eligible"] += 1
                if apply and with_drift:
                    _queue_drift(candidate, lat, lon)
            else:
                report["drift_rejected"] += 1
        _log(candidate, f"{lat:.5f},{lon:.5f} via {method} -> {outcome}")

    report["dry_run"] = not apply
    return report


def _log(candidate: dict, status: str) -> None:
    logger.info(
        "%-14s %s  %s  -> %s",
        str(candidate["id"])[:14], candidate.get("timestamp_utc"),
        (candidate.get("title") or "")[:48], status,
    )


def _queue_drift(candidate: dict, lat: float, lon: float) -> None:
    try:
        from core.intel.drift_service import schedule_intel_drift

        schedule_intel_drift(
            candidate["id"], lat, lon,
            candidate.get("persons"), candidate.get("vessel_type") or "rubber_boat",
            candidate.get("timestamp_utc") or datetime.now(timezone.utc).isoformat(),
            force=True,
            background=False,
        )
    except Exception as exc:
        logger.warning("backfill drift failed for %s: %s", candidate["id"], exc)


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
