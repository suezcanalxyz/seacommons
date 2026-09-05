"""Bounded satellite enrichment for operationally meaningful intel events."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from core.intel.lifecycle import parse_utc
from core.intel.satellite_observation import persist_observations
from core.intel.satellite_resolver import resolve_for_incident

logger = logging.getLogger(__name__)

SATELLITE_HISTORY_DAYS = 7
SATELLITE_RECHECK_MINUTES = 30
_DIRECTIONS = ("reverse", "nearest", "forward")


def is_satellite_enrichment_candidate(event, *, now: datetime | None = None) -> bool:
    """Select sparse incident-level signals, never raw high-volume AIS pings."""
    if event.lat is None or event.lon is None:
        return False
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    observed = parse_utc(event.timestamp_utc)
    if observed is not None and now - observed > timedelta(days=SATELLITE_HISTORY_DAYS):
        return False

    meta = event.metadata or {}
    meaningful = bool(
        meta.get("is_distress")
        or meta.get("publication_status") == "published"
        or meta.get("drift_eligible")
    )
    if not meaningful:
        return False
    return True


def _is_due(event, *, now: datetime) -> bool:
    checked = parse_utc(str((event.metadata or {}).get("satellite_last_checked_at") or ""))
    return checked is None or now - checked >= timedelta(minutes=SATELLITE_RECHECK_MINUTES)


def enrich_event(
    event,
    *,
    now: datetime | None = None,
    provider=None,
    include_viirs: bool = True,
) -> dict[str, int]:
    """Collect reverse/nearest/forward evidence without blocking on one failure."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    event_time = parse_utc(event.timestamp_utc) or now
    report = {"persisted": 0, "errors": 0}
    for direction in _DIRECTIONS:
        try:
            observations = resolve_for_incident(
                incident_id=event.id,
                lat=float(event.lat), lon=float(event.lon),
                event_time=event_time,
                direction=direction,
                provider=provider,
                include_viirs=include_viirs,
                now=now,
            )
            report["persisted"] += persist_observations(observations)
        except Exception as exc:
            report["errors"] += 1
            logger.info(
                "Satellite %s lookup unavailable for event=%s: %s",
                direction, event.id, type(exc).__name__,
            )
    return report


def enrich_recent_events(*, limit: int = 6, now: datetime | None = None) -> dict[str, int]:
    """Enrich a bounded batch so public providers are never hammered."""
    from core.intel.store import intel_store

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    events = intel_store.events(limit=300, max_age_days=SATELLITE_HISTORY_DAYS)
    report = {"scanned": len(events), "enriched": 0, "persisted": 0, "errors": 0}

    for event in events:
        if report["enriched"] >= limit:
            break
        if not is_satellite_enrichment_candidate(event, now=now) or not _is_due(event, now=now):
            continue
        result = enrich_event(event, now=now)
        report["enriched"] += 1
        report["persisted"] += result["persisted"]
        report["errors"] += result["errors"]
        intel_store.update_metadata(
            event.id,
            metadata={
                "satellite_last_checked_at": now.isoformat(),
                "satellite_last_new_observations": result["persisted"],
                "satellite_last_errors": result["errors"],
            },
        )
    return report
