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
        existing_ids = {
            incident_id for (incident_id,) in db.query(HumanitarianIncidentDB.incident_id).all()
        }
        rows = (
            db.query(IntelEventDB)
            .filter(IntelEventDB.timestamp_utc >= cutoff)
            .order_by(IntelEventDB.timestamp_utc.desc())
            .yield_per(1000)
        )
        source_context: dict[str, list[IntelEvent]] = {}
        candidates: list[HumanitarianIncidentBackfillCandidate] = []
        for row in rows:
            if row.id in existing_ids:
                continue
            event = _event_from_row(row)
            if classify_service(event).service != "humanitarian":
                continue
            if event.source not in source_context:
                context_rows = (
                    db.query(IntelEventDB)
                    .filter(
                        IntelEventDB.timestamp_utc >= cutoff,
                        IntelEventDB.source == event.source,
                    )
                    .order_by(IntelEventDB.timestamp_utc.desc())
                    .limit(250)
                    .all()
                )
                source_context[event.source] = [_event_from_row(item) for item in context_rows]
            lifecycle = distress_lifecycle(
                event, now=now,
                same_source=[other for other in source_context[event.source] if other.id != event.id],
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


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Dry-run is the default; writes require --apply."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Backfill canonical HumanitarianIncident rows")
    parser.add_argument("--apply", action="store_true", help="persist changes (default: dry-run)")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args(argv)
    report = run(apply=args.apply, limit=max(1, args.limit), days=max(1, args.days))
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
