"""Backfill canonical HumanitarianIncident rows from durable IntelEvents.

Dry-run first by default. This repairs pre-P0.3 events without inventing
correlation: each legacy event keeps its own event id as incident id.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.intel.store import IntelEvent


@dataclass(frozen=True)
class HumanitarianIncidentBackfillCandidate:
    event: IntelEvent
    lifecycle: str
    case_type: str | None

    @property
    def event_id(self) -> str:
        return self.event.id


def _event_from_row(row) -> IntelEvent:
    meta = dict(row.meta or {})
    if getattr(row, "maritime_domain", None) and not meta.get("maritime_domain"):
        meta["maritime_domain"] = row.maritime_domain
    return IntelEvent(
        id=row.id, timestamp_utc=row.timestamp_utc, type=row.type,
        severity=row.severity, lat=row.lat, lon=row.lon,
        title=row.title or "", text=row.text or "", url=row.url or "",
        source=row.source or "", linked_mmsi=row.linked_mmsi or "",
        metadata=meta,
    )


def find_candidates(*, limit: int = 500, days: int = 30) -> list[HumanitarianIncidentBackfillCandidate]:
    from core.db.models import HumanitarianIncidentDB, IntelEventDB
    from core.db.session import session_scope
    from core.intel.lifecycle import distress_lifecycle
    from core.intel.service_taxonomy import classify_service

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=max(1, days))).isoformat()
    with session_scope() as db:
        rows = (
            db.query(IntelEventDB)
            .filter(IntelEventDB.timestamp_utc >= cutoff)
            .order_by(IntelEventDB.timestamp_utc.desc())
            .limit(max(limit * 4, limit))
            .all()
        )
        events = [_event_from_row(row) for row in rows]
        by_source: dict[str, list[IntelEvent]] = {}
        for event in events:
            by_source.setdefault(event.source, []).append(event)

        candidates: list[HumanitarianIncidentBackfillCandidate] = []
        for event in events:
            if db.get(HumanitarianIncidentDB, event.id) is not None:
                continue
            if classify_service(event).service != "humanitarian":
                continue
            lifecycle = distress_lifecycle(
                event, now=now,
                same_source=[other for other in by_source.get(event.source, []) if other.id != event.id],
            )
            candidates.append(HumanitarianIncidentBackfillCandidate(
                event=event,
                lifecycle=lifecycle,
                case_type=event.metadata.get("humanitarian_case_type") or event.metadata.get("case_type"),
            ))
            if len(candidates) >= limit:
                break
    return candidates


def run(*, apply: bool = False, limit: int = 500, days: int = 30) -> dict[str, int]:
    from core.intel.humanitarian_incident import sync_incident_for_event

    candidates = find_candidates(limit=limit, days=days)
    report = {"scanned": len(candidates), "created": 0}
    if not apply:
        return report

    for candidate in candidates:
        sync_incident_for_event(
            candidate.event,
            lifecycle=candidate.lifecycle,
            case_type=candidate.case_type,
        )
        report["created"] += 1
    return report
