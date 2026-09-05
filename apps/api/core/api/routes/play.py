"""Public Play: privacy-safe temporal reconstruction of incidents."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.intel.humanitarian_incident import public_incident_status
from core.intel.lifecycle import parse_utc
from core.intel.public_policy import domains_for_mode
from core.intel.store import IntelEvent
from core.live.projection import public_archive_event_types, public_intel_feature

router = APIRouter(prefix="/api/v1/play", tags=["play"])


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    parsed = parse_utc(str(value))
    return parsed.isoformat() if parsed else str(value)


def _status_for_row(row, *, now: datetime) -> str:
    return public_incident_status({
        "lifecycle": row.lifecycle,
        "incident_status": row.incident_status,
        "last_update_at": row.last_update_at,
    }, now=now)


def _belongs_to_play(row, *, now: datetime) -> bool:
    status = _status_for_row(row, now=now)
    if status in {"resolved", "outcome_unknown"}:
        return True
    last = parse_utc(row.last_update_at or row.reported_at or "")
    return bool(last and (now - last).total_seconds() >= 24 * 3600)


def _incident_projection(row, event, *, now: datetime) -> dict[str, Any]:
    status = _status_for_row(row, now=now)
    geometry = None
    if event is not None and event.lat is not None and event.lon is not None:
        geometry = {"type": "Point", "coordinates": [event.lon, event.lat]}
    return {
        "incident_id": row.incident_id,
        "incident_status": status,
        "surface": "play",
        "case_type": row.case_type,
        "reported_at": row.reported_at,
        "last_update_at": row.last_update_at,
        "state_changed_at": _iso(row.state_changed_at),
        "resolved_at": _iso(row.resolved_at),
        "title": event.title if event is not None else "Humanitarian incident",
        "source": event.source if event is not None else None,
        "geometry": geometry,
        "domain": "humanitarian",
    }


def _generic_maritime_status(event) -> str:
    meta = dict(event.meta or {})
    raw = str(meta.get("incident_status") or meta.get("lifecycle") or "").lower()
    if raw == "resolved":
        return "resolved"
    if raw == "needs_review":
        return "needs_review"
    return "outcome_unknown"


def _intel_event_from_row(event) -> IntelEvent:
    meta = dict(event.meta or {})
    if event.maritime_domain and not meta.get("maritime_domain"):
        meta["maritime_domain"] = event.maritime_domain
    return IntelEvent(
        id=event.id, timestamp_utc=event.timestamp_utc, type=event.type,
        severity=event.severity, lat=event.lat, lon=event.lon,
        title=event.title or "", text=event.text or "", url=event.url or "",
        source=event.source or "", linked_mmsi=event.linked_mmsi or "", metadata=meta,
    )


def _is_public_historical_maritime(event, *, now: datetime) -> bool:
    if event.lat is None or event.lon is None:
        return False
    at = parse_utc(event.timestamp_utc or "")
    if not at or (now - at).total_seconds() < 24 * 3600:
        return False
    return public_intel_feature(
        _intel_event_from_row(event), allowed_domains=domains_for_mode("all")
    ) is not None


def _generic_maritime_projection(event) -> dict[str, Any]:
    return {
        "incident_id": event.id,
        "incident_status": _generic_maritime_status(event),
        "surface": "play",
        "case_type": event.type,
        "reported_at": event.timestamp_utc,
        "last_update_at": event.timestamp_utc,
        "state_changed_at": None,
        "resolved_at": None,
        "title": event.title or "Maritime incident",
        "source": event.source,
        "geometry": {"type": "Point", "coordinates": [event.lon, event.lat]},
        "domain": "maritime",
    }


@router.get("/counts")
async def play_counts():
    """Exact public archive counters, independent of page/transport size."""
    from core.db.models import HumanitarianIncidentDB, IntelEventDB
    from core.db.session import session_scope

    now = datetime.now(timezone.utc)
    cutoff = datetime.fromtimestamp(now.timestamp() - 24 * 3600, tz=timezone.utc).isoformat()
    with session_scope() as db:
        human_rows = db.query(HumanitarianIncidentDB).all()
        human_ids = {row.incident_id for row in human_rows}
        humanitarian_count = sum(1 for row in human_rows if _belongs_to_play(row, now=now))
        maritime_count = 0
        rows = (
            db.query(IntelEventDB)
            .filter(
                IntelEventDB.type.in_(public_archive_event_types()),
                IntelEventDB.timestamp_utc <= cutoff,
                IntelEventDB.lat.isnot(None),
                IntelEventDB.lon.isnot(None),
            )
            .yield_per(1000)
        )
        for event in rows:
            if event.id in human_ids:
                continue
            if _is_public_historical_maritime(event, now=now):
                maritime_count += 1
    return {
        "total_count": humanitarian_count + maritime_count,
        "humanitarian_count": humanitarian_count,
        "maritime_count": maritime_count,
        "generated_at": now.isoformat(),
    }


@router.get("/incidents")
async def play_incidents(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    from core.db.models import HumanitarianIncidentDB, IncidentTransitionDB, IntelEventDB
    from core.db.session import session_scope

    now = datetime.now(timezone.utc)
    historical_cutoff = (now.timestamp() - 24 * 3600)
    historical_cutoff_iso = datetime.fromtimestamp(historical_cutoff, tz=timezone.utc).isoformat()
    need = offset + limit + 1
    candidate_cap = max(2000, need * 8)
    combined: list[dict[str, Any]] = []
    human_ids: set[str] = set()

    with session_scope() as db:
        rows = (
            db.query(HumanitarianIncidentDB)
            .order_by(HumanitarianIncidentDB.last_update_at.desc())
            .limit(candidate_cap)
            .all()
        )
        for row in rows:
            human_ids.add(row.incident_id)
            if not _belongs_to_play(row, now=now):
                continue
            event = db.get(IntelEventDB, row.incident_id)
            combined.append(_incident_projection(row, event, now=now))

        maritime_rows = (
            db.query(IntelEventDB)
            .filter(
                IntelEventDB.type.in_(public_archive_event_types()),
                IntelEventDB.timestamp_utc <= historical_cutoff_iso,
                IntelEventDB.lat.isnot(None),
                IntelEventDB.lon.isnot(None),
            )
            .order_by(IntelEventDB.timestamp_utc.desc())
            .limit(candidate_cap)
            .all()
        )
        for event in maritime_rows:
            if event.id in human_ids or not _is_public_historical_maritime(event, now=now):
                continue
            combined.append(_generic_maritime_projection(event))

        combined.sort(
            key=lambda item: str(item.get("last_update_at") or item.get("reported_at") or ""),
            reverse=True,
        )
        page = combined[offset:offset + limit]

        page_human_ids = [item["incident_id"] for item in page if item.get("domain") == "humanitarian"]
        history: dict[str, list[dict[str, Any]]] = {incident_id: [] for incident_id in page_human_ids}
        if page_human_ids:
            transitions = (
                db.query(IncidentTransitionDB)
                .filter(IncidentTransitionDB.incident_id.in_(page_human_ids))
                .order_by(IncidentTransitionDB.transition_at.asc())
                .all()
            )
            for transition in transitions:
                history.setdefault(transition.incident_id, []).append({
                    "at": _iso(transition.transition_at),
                    "from_state": transition.from_state,
                    "to_state": transition.to_state,
                })
        for item in page:
            item["status_history"] = history.get(item["incident_id"], [])

    next_offset = offset + len(page) if len(combined) > offset + len(page) else None
    return {
        "incidents": page,
        "offset": offset,
        "next_offset": next_offset,
        "generated_at": now.isoformat(),
    }


def _thread_item(incident_id: str, repost: dict, *, reported_at: str | None) -> dict[str, Any] | None:
    at = _iso(repost.get("posted_at"))
    if not at:
        return None
    note = str(repost.get("note") or "").strip()
    from core.intel.geoextract import is_concluded_incident

    if note and is_concluded_incident(note):
        item_type = "resolution"
    else:
        reported = parse_utc(reported_at or "")
        posted = parse_utc(at)
        item_type = (
            "attending_news"
            if reported and posted and (posted - reported).total_seconds() >= 24 * 3600
            else "update"
        )
    return {
        "id": str(repost.get("tweet_id") or f"update:{incident_id}:{at}"),
        "at": at,
        "type": item_type,
        "source": "source_update",
        "title": note or "Source update",
        "geometry": None,
        "properties": {
            "url": repost.get("url"),
            "kind": repost.get("kind"),
        },
    }


def _transition_item(row) -> dict[str, Any]:
    return {
        "id": row.transition_id,
        "at": _iso(row.transition_at),
        "type": "resolution" if row.to_state == "resolved" else "status",
        "source": "incident_state",
        "title": f"Status: {row.to_state}",
        "geometry": None,
        "properties": {
            "from_state": row.from_state,
            "to_state": row.to_state,
            "reason_code": row.reason_code,
            "review_required": bool(row.review_required),
        },
    }


def _drift_item(row) -> dict[str, Any]:
    metadata = dict(row.metadata_json or {})
    return {
        "id": row.drift_id,
        "at": _iso(row.created_at),
        "type": "drift",
        "source": "SeaCommons/OpenDrift",
        "title": "Drift forecast computed",
        "geometry": row.trajectory,
        "properties": {
            "drift_id": row.drift_id,
            "domain": row.domain,
            "model": metadata.get("model") or row.model_version or "OpenDrift",
            "forecast": True,
            "cone_24h": row.cone_24h,
            "impact_point": row.impact_point,
        },
    }


@router.get("/incidents/{incident_id}/timeline")
async def play_incident_timeline(incident_id: str):
    from sqlalchemy import or_

    from core.db.models import (
        DriftResultDB,
        HumanitarianIncidentDB,
        IncidentTransitionDB,
        IntelEventDB,
        SatelliteObservationDB,
    )
    from core.db.session import session_scope

    now = datetime.now(timezone.utc)
    with session_scope() as db:
        incident = db.get(HumanitarianIncidentDB, incident_id)
        event = db.get(IntelEventDB, incident_id)
        generic_maritime = incident is None and event is not None and _is_public_historical_maritime(event, now=now)
        if incident is None and not generic_maritime:
            raise HTTPException(status_code=404, detail="Incident not found")
        if incident is not None and not _belongs_to_play(incident, now=now):
            raise HTTPException(status_code=404, detail="Incident is still operationally Live")
        incident_status = _status_for_row(incident, now=now) if incident is not None else _generic_maritime_status(event)
        domain = "humanitarian" if incident is not None else "maritime"
        timeline: list[dict[str, Any]] = []
        if event is not None:
            geometry = None
            if event.lat is not None and event.lon is not None:
                geometry = {"type": "Point", "coordinates": [event.lon, event.lat]}
            timeline.append({
                "id": f"report:{incident_id}",
                "at": _iso(event.timestamp_utc),
                "type": "report",
                "source": event.source,
                "title": event.title,
                "geometry": geometry,
                "properties": {"url": event.url or None},
            })
            for repost in (event.meta or {}).get("thread_reposts") or []:
                item = _thread_item(incident_id, repost, reported_at=incident.reported_at if incident is not None else event.timestamp_utc)
                if item is not None:
                    timeline.append(item)
        if incident is not None:
            transitions = (
                db.query(IncidentTransitionDB)
                .filter(IncidentTransitionDB.incident_id == incident_id)
                .order_by(IncidentTransitionDB.transition_at.asc())
                .all()
            )
            timeline.extend(_transition_item(row) for row in transitions)

        drifts = (
            db.query(DriftResultDB)
            .filter(
                DriftResultDB.status == "completed",
                or_(
                    DriftResultDB.event_id == incident_id,
                    DriftResultDB.event_id == f"intel:{incident_id}",
                ),
            )
            .order_by(DriftResultDB.created_at.asc())
            .all()
        )
        timeline.extend(_drift_item(row) for row in drifts)

        satellites = (
            db.query(SatelliteObservationDB)
            .filter(SatelliteObservationDB.incident_id == incident_id)
            .order_by(SatelliteObservationDB.acquisition_time.asc())
            .all()
        )
        timeline.extend(_satellite_item(row) for row in satellites)

    timeline = [item for item in timeline if item.get("at")]
    timeline.sort(key=lambda item: item["at"])
    return {
        "incident_id": incident_id,
        "incident_status": incident_status,
        "surface": "play",
        "domain": domain,
        "timeline": timeline,
        "generated_at": now.isoformat(),
    }


def _satellite_item(row) -> dict[str, Any]:
    return {
        "id": row.observation_id,
        "at": _iso(row.acquisition_time),
        "type": "satellite",
        "source": row.provider,
        "title": f"{row.mission} observation",
        "geometry": row.footprint,
        "properties": {
            "mission": row.mission,
            "product_id": row.product_id,
            "sensor_type": row.sensor_type,
            "temporal_relation": row.temporal_relation,
            "temporal_delta_s": row.temporal_delta_s,
            "asset_ref": row.asset_ref,
            "source_url": row.source_url,
            "bbox": row.bbox,
            "resolution_m": row.resolution_m,
            "cloud_cover": row.cloud_cover,
            "polarisation": row.polarisation,
            "evidence_status": row.evidence_status,
            "provenance": row.provenance or {},
        },
    }
