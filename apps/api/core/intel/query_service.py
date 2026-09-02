# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read models for intelligence API routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.intel.store import IntelEvent, event_feature_with_lifecycle, intel_store


class ArchiveQueryError(RuntimeError):
    """The durable intelligence archive could not be queried."""


def intel_collection(
    *,
    severity: str | None,
    type_filter: str | None,
    tier: str | None,
    limit: int,
    days: int,
) -> dict:
    events = intel_store.events(
        severity=severity,
        type_filter=type_filter,
        limit=limit,
        max_age_days=days,
    )
    if tier:
        events = [event for event in events if event.tier() == tier]

    # Stable passes preserve newest-first ordering within each priority.
    events.sort(key=lambda event: event.timestamp_utc or "", reverse=True)
    events.sort(key=lambda event: event.priority())

    with_coords = [event for event in events if event.lat is not None and event.lon is not None]
    operational = [event for event in events if event.tier() == "operational"]
    by_source: dict[str, list[IntelEvent]] = {}
    for event in events:
        by_source.setdefault(event.source, []).append(event)

    return {
        "type": "FeatureCollection",
        "features": [
            event_feature_with_lifecycle(event, same_source=by_source.get(event.source, []))
            for event in events
        ],
        "meta": {
            "total": len(events),
            "with_coords": len(with_coords),
            "no_coords_count": len(events) - len(with_coords),
            "operational_count": len(operational),
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }


def source_health() -> dict:
    from core.intel.source_registry import source_registry

    sources = source_registry.get_all()
    return {
        "sources": sources,
        "summary": {
            "total": len(sources),
            "active": sum(1 for source in sources if source["status"] == "active"),
            "degraded": sum(1 for source in sources if source["status"] == "degraded"),
            "offline": sum(1 for source in sources if source["status"] == "offline"),
        },
    }


def geolocated_event_collection(
    *,
    type_filter: str,
    limit: int,
    severity: str | None = None,
    include_missing_count: bool = False,
) -> dict:
    events = intel_store.events(severity=severity, type_filter=type_filter, limit=limit)
    features = [event.to_geojson_feature() for event in events if event.lat is not None]
    meta = {"count": len(features)}
    if include_missing_count:
        meta["no_coords"] = len(events) - len(features)
    return {"type": "FeatureCollection", "features": features, "meta": meta}


def archive_collection(
    *,
    days: int,
    severity: str | None,
    type_filter: str | None,
    limit: int,
    fmt: str,
) -> dict:
    from core.db.models import IntelEventDB
    from core.db.session import session_scope

    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    try:
        with session_scope() as db:
            query = db.query(IntelEventDB).filter(IntelEventDB.timestamp_utc >= cutoff)
            if severity:
                query = query.filter(IntelEventDB.severity == severity)
            if type_filter:
                query = query.filter(IntelEventDB.type == type_filter)
            rows = query.order_by(IntelEventDB.timestamp_utc.desc()).limit(limit).all()
    except Exception as exc:
        raise ArchiveQueryError(str(exc)) from exc

    if fmt == "json":
        return {
            "events": [
                {
                    "id": row.id,
                    "timestamp_utc": row.timestamp_utc,
                    "type": row.type,
                    "severity": row.severity,
                    "lat": row.lat,
                    "lon": row.lon,
                    "title": row.title,
                    "source": row.source,
                    "url": row.url,
                    "meta": row.meta or {},
                }
                for row in rows
            ],
            "meta": {"count": len(rows), "days": days},
        }

    features = [
        {
            "type": "Feature",
            "geometry": (
                {"type": "Point", "coordinates": [row.lon, row.lat]}
                if row.lat and row.lon
                else None
            ),
            "properties": {
                "id": row.id,
                "type": row.type,
                "severity": row.severity,
                "title": row.title,
                "source": row.source,
                "url": row.url,
                "timestamp_utc": row.timestamp_utc,
                **(row.meta or {}),
            },
        }
        for row in rows
    ]
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {"count": len(features), "days": days},
    }


def intel_drift_collection() -> dict:
    from core.db.store import get_drift

    features = []
    for event in intel_store.events(limit=500):
        job_id = event.metadata.get("drift_job_id")
        if not job_id or event.metadata.get("drift_status") != "completed":
            continue
        drift = get_drift(job_id)
        if not drift or drift.get("status") != "completed":
            continue
        from core.domain.visual_category import visual_category_fields

        category = visual_category_fields(
            source=event.source,
            event_type=event.type,
            maritime_domain=event.maritime_domain(),
            humanitarian_case_type=event.metadata.get("humanitarian_case_type"),
            metadata=event.metadata,
        )
        for feature in (drift.get("trajectory"), drift.get("cone_24h")):
            if feature:
                projected = dict(feature)
                properties = dict(projected.get("properties") or {})
                properties.update(
                    {
                        "intel_event_id": event.id,
                        "intel_title": event.title[:80],
                        "intel_source": event.source,
                        "origin_category": category["visual_category"],
                        "visual_category": category["visual_category"],
                        "visual_color": category["visual_color"],
                        "category_label": category["category_label"],
                        "auto_drift": True,
                    }
                )
                projected["properties"] = properties
                features.append(projected)
        for feature in (drift.get("impact_point") or {}).get("features", []):
            projected = dict(feature)
            properties = dict(projected.get("properties") or {})
            properties["intel_event_id"] = event.id
            properties["auto_drift"] = True
            projected["properties"] = properties
            features.append(projected)

    return {"type": "FeatureCollection", "features": features}
