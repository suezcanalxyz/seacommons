# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any

from sqlalchemy import func

from core.db.models import IntelEventDB, MaritimeEpisodeDB, SatelliteObservationDB, VesselTrackDB
from core.db.session import session_scope


def _utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    a1, a2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    h = math.sin(dlat / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(max(0.0, min(1.0, h))))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a1, a2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(a2)
    x = math.cos(a1) * math.sin(a2) - math.sin(a1) * math.cos(a2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _course_alignment(course: float | None, bearing: float) -> float | None:
    if course is None:
        return None
    delta = min(abs(float(course) - bearing), 360.0 - abs(float(course) - bearing))
    return max(0.0, 1.0 - delta / 180.0)


def satellite_coverage_queue(
    *,
    hours: int = 168,
    temporal_hours: float = 12.0,
    limit: int = 100,
) -> dict[str, Any]:
    """Context-only satellite coverage queue.

    A scene covering an episode in space/time is NOT evidence of the episode.
    This queue merely identifies scenes worth review. Only explicit strong
    satellite associations can contribute an independent lineage.
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=hours)).replace(tzinfo=None)
    with session_scope() as db:
        episodes = [
            {
                "episode_id": row.episode_id,
                "episode_family": row.episode_family,
                "verification_status": row.verification_status,
                "start_at": row.start_at,
                "end_at": row.end_at,
                "geometry": row.geometry,
            }
            for row in (
                db.query(MaritimeEpisodeDB)
                .filter(MaritimeEpisodeDB.updated_at >= cutoff)
                .order_by(MaritimeEpisodeDB.updated_at.desc())
                .limit(1500)
                .all()
            )
        ]
        satellite = [
            {
                "observation_id": row.observation_id,
                "provider": row.provider,
                "mission": row.mission,
                "acquisition_time": row.acquisition_time,
                "bbox": row.bbox,
                "association_status": row.association_status,
                "evidence_status": row.evidence_status,
                "episode_id": row.episode_id,
                "asset_ref": row.asset_ref,
                "source_url": row.source_url,
            }
            for row in (
                db.query(SatelliteObservationDB)
                .filter(
                    SatelliteObservationDB.created_at >= cutoff,
                    SatelliteObservationDB.bbox.isnot(None),
                )
                .order_by(SatelliteObservationDB.created_at.desc())
                .limit(6000)
                .all()
            )
        ]

    rows: list[dict[str, Any]] = []
    family_weight = {
        "spoofing_episode": 1.0,
        "rendezvous_episode": 0.9,
        "identity_integrity_episode": 0.9,
        "infrastructure_proximity_episode": 0.85,
        "gap_episode": 0.75,
        "safety_episode": 0.55,
    }
    window = timedelta(hours=temporal_hours)
    for episode in episodes:
        geometry = episode["geometry"] if isinstance(episode.get("geometry"), dict) else {}
        if geometry.get("type") != "Point":
            continue
        coords = geometry.get("coordinates") or ()
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        start = _utc(episode.get("start_at"))
        end = _utc(episode.get("end_at")) or start
        if start is None:
            continue
        scenes: list[dict[str, Any]] = []
        for scene in satellite:
            if scene.get("episode_id") and str(scene.get("episode_id")) == str(episode["episode_id"]) and scene.get("association_status") == "strong":
                continue
            bbox = scene.get("bbox") if isinstance(scene.get("bbox"), list) else None
            if not bbox or len(bbox) != 4:
                continue
            x0, y0, x1, y1 = map(float, bbox)
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            acquired = _utc(scene.get("acquisition_time"))
            if acquired is None or acquired < start - window or acquired > end + window:
                continue
            if acquired < start:
                delta_h = (start - acquired).total_seconds() / 3600.0
            elif acquired > end:
                delta_h = (acquired - end).total_seconds() / 3600.0
            else:
                delta_h = 0.0
            scenes.append({
                "observation_id": scene.get("observation_id"),
                "provider": scene.get("provider"),
                "mission": scene.get("mission"),
                "acquisition_time": acquired.isoformat(),
                "delta_hours": round(delta_h, 3),
                "association_status": scene.get("association_status") or "coverage_context",
                "evidence_status": scene.get("evidence_status"),
                "asset_ref": scene.get("asset_ref"),
                "source_url": scene.get("source_url"),
            })
        if not scenes:
            continue
        scenes.sort(key=lambda item: item["delta_hours"])
        nearest = scenes[0]["delta_hours"]
        score = family_weight.get(str(episode["episode_family"]), 0.5) + max(0.0, 1.0 - nearest / max(temporal_hours, 0.1))
        rows.append({
            "episode_id": episode["episode_id"],
            "episode_family": episode["episode_family"],
            "verification_status": episode["verification_status"],
            "scene_count": len(scenes),
            "nearest_delta_hours": nearest,
            "priority_score": round(score, 3),
            "geometry": geometry,
            "scenes": scenes[:5],
            "evidence_role": "context_only_pending_review",
        })
    rows.sort(key=lambda item: (-item["priority_score"], item["nearest_delta_hours"]))
    return {
        "generated_at": now.isoformat(),
        "lookback_hours": hours,
        "temporal_window_hours": temporal_hours,
        "count": min(limit, len(rows)),
        "total_candidates": len(rows),
        "items": rows[:limit],
        "semantics": "Spatial/temporal satellite coverage is context for review, not corroborating evidence.",
    }


def humanitarian_ais_correlation(
    *,
    hours: int = 168,
    radius_nm: float = 35.0,
    window_hours: float = 2.0,
    limit: int = 50,
    candidates_per_event: int = 8,
) -> dict[str, Any]:
    """Find contextual AIS response candidates around geolocated humanitarian reports.

    The result never assigns casualty identity. An exact MMSI already present
    in the humanitarian event can be marked strong; all proximity-only matches
    remain contextual.
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=hours)).replace(tzinfo=None)
    humanitarian_sources = (
        "alarm_phone", "alarm phone", "sosmedintl", "msf_sea", "seawatchcrew",
        "sea watch", "sos méditerranée", "sos mediterranee",
    )
    with session_scope() as db:
        events = [
            {
                "id": row.id,
                "source": row.source,
                "title": row.title,
                "timestamp_utc": row.timestamp_utc,
                "created_at": row.created_at,
                "lat": row.lat,
                "lon": row.lon,
                "linked_mmsi": row.linked_mmsi,
            }
            for row in (
                db.query(IntelEventDB)
                .filter(
                    IntelEventDB.created_at >= cutoff,
                    IntelEventDB.lat.isnot(None),
                    IntelEventDB.lon.isnot(None),
                    func.lower(IntelEventDB.source).in_(humanitarian_sources),
                )
                .order_by(IntelEventDB.created_at.desc())
                .limit(250)
                .all()
            )
        ]

    from core.vessels.registry import registry
    registry_cache = getattr(registry, "_cache", {}) or {}
    out: list[dict[str, Any]] = []
    radius_km = radius_nm * 1.852
    for event in events:
        observed = _utc(event.get("timestamp_utc")) or _utc(event.get("created_at"))
        if observed is None:
            continue
        lat, lon = float(event["lat"]), float(event["lon"])
        lat_pad = radius_km / 111.0
        lon_pad = radius_km / max(20.0, 111.0 * math.cos(math.radians(lat)))
        lo = (observed - timedelta(hours=window_hours)).replace(tzinfo=None)
        hi = (observed + timedelta(hours=window_hours)).replace(tzinfo=None)
        with session_scope() as db:
            tracks = [
                {
                    "mmsi": row.mmsi,
                    "ts": row.ts,
                    "lat": row.lat,
                    "lon": row.lon,
                    "sog": row.sog,
                    "cog": row.cog,
                }
                for row in (
                    db.query(VesselTrackDB)
                    .filter(
                        VesselTrackDB.ts >= lo,
                        VesselTrackDB.ts <= hi,
                        VesselTrackDB.lat.between(lat - lat_pad, lat + lat_pad),
                        VesselTrackDB.lon.between(lon - lon_pad, lon + lon_pad),
                    )
                    .order_by(VesselTrackDB.ts.asc())
                    .limit(8000)
                    .all()
                )
            ]
        best: dict[str, dict[str, Any]] = {}
        for track in tracks:
            distance_km = _haversine_km(lat, lon, float(track["lat"]), float(track["lon"]))
            if distance_km > radius_km:
                continue
            track_ts = track["ts"].replace(tzinfo=timezone.utc) if track["ts"].tzinfo is None else track["ts"]
            dt_s = abs((track_ts - observed).total_seconds())
            bearing = _bearing(float(track["lat"]), float(track["lon"]), lat, lon)
            alignment = _course_alignment(track.get("cog"), bearing)
            distance_score = max(0.0, 1.0 - distance_km / radius_km)
            time_score = max(0.0, 1.0 - dt_s / max(1.0, window_hours * 3600.0))
            heading_score = alignment if alignment is not None else 0.25
            score = 0.50 * distance_score + 0.30 * time_score + 0.20 * heading_score
            mmsi = str(track["mmsi"])
            current = best.get(mmsi)
            if current is not None and float(current["score"]) >= score:
                continue
            vessel = dict(registry_cache.get(mmsi, {}) or {})
            exact = bool(event.get("linked_mmsi") and str(event.get("linked_mmsi")) == mmsi)
            best[mmsi] = {
                "mmsi": mmsi,
                "ship_name": vessel.get("ship_name") or mmsi,
                "imo": vessel.get("imo"),
                "ship_type": vessel.get("ship_type"),
                "flag": vessel.get("flag"),
                "distance_km": round(distance_km, 2),
                "distance_nm": round(distance_km / 1.852, 2),
                "time_delta_seconds": round(dt_s, 1),
                "speed_kn": track.get("sog"),
                "course_deg": track.get("cog"),
                "bearing_to_report_deg": round(bearing, 1),
                "heading_alignment": round(alignment, 3) if alignment is not None else None,
                "score": round(score, 3),
                "association_status": "strong_identity_link" if exact else "contextual_response_candidate",
                "evidence_role": "corroboration" if exact else "context_only",
            }
        candidates = sorted(best.values(), key=lambda item: (-item["score"], item["distance_km"]))[:candidates_per_event]
        out.append({
            "event_id": event["id"],
            "source": event["source"],
            "title": event["title"],
            "timestamp_utc": event["timestamp_utc"],
            "lat": lat,
            "lon": lon,
            "linked_mmsi": event.get("linked_mmsi") or None,
            "candidate_count": len(candidates),
            "candidates": candidates,
        })
    out.sort(key=lambda item: item["timestamp_utc"] or "", reverse=True)
    return {
        "generated_at": now.isoformat(),
        "lookback_hours": hours,
        "radius_nm": radius_nm,
        "window_hours": window_hours,
        "count": min(limit, len(out)),
        "items": out[:limit],
        "semantics": "Proximity, timing and convergence are contextual unless the humanitarian source itself supplies a vessel identity.",
    }


def satellite_context_for_episode(
    episode_id: str,
    *,
    temporal_hours: float = 12.0,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return coverage-only satellite scenes worth reviewing for one dossier."""
    with session_scope() as db:
        episode = db.get(MaritimeEpisodeDB, str(episode_id))
        if episode is None:
            return []
        snapshot = {
            "episode_id": episode.episode_id,
            "start_at": episode.start_at,
            "end_at": episode.end_at,
            "geometry": episode.geometry,
        }
        scenes = [
            {
                "observation_id": row.observation_id,
                "provider": row.provider,
                "mission": row.mission,
                "acquisition_time": row.acquisition_time,
                "bbox": row.bbox,
                "association_status": row.association_status,
                "evidence_status": row.evidence_status,
                "episode_id": row.episode_id,
                "asset_ref": row.asset_ref,
                "source_url": row.source_url,
            }
            for row in (
                db.query(SatelliteObservationDB)
                .filter(SatelliteObservationDB.bbox.isnot(None))
                .order_by(SatelliteObservationDB.created_at.desc())
                .limit(3000)
                .all()
            )
        ]

    geometry = snapshot["geometry"] if isinstance(snapshot.get("geometry"), dict) else {}
    if geometry.get("type") != "Point":
        return []
    coords = geometry.get("coordinates") or ()
    if len(coords) < 2:
        return []
    lon, lat = float(coords[0]), float(coords[1])
    start = _utc(snapshot.get("start_at"))
    end = _utc(snapshot.get("end_at")) or start
    if start is None:
        return []
    window = timedelta(hours=temporal_hours)
    candidates: list[dict[str, Any]] = []
    for scene in scenes:
        if (
            scene.get("episode_id")
            and str(scene.get("episode_id")) == str(episode_id)
            and scene.get("association_status") == "strong"
        ):
            continue
        bbox = scene.get("bbox") if isinstance(scene.get("bbox"), list) else None
        if not bbox or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = map(float, bbox)
        if not (x0 <= lon <= x1 and y0 <= lat <= y1):
            continue
        acquired = _utc(scene.get("acquisition_time"))
        if acquired is None or acquired < start - window or acquired > end + window:
            continue
        if acquired < start:
            delta_h = (start - acquired).total_seconds() / 3600.0
        elif acquired > end:
            delta_h = (acquired - end).total_seconds() / 3600.0
        else:
            delta_h = 0.0
        candidates.append({
            "observation_id": scene.get("observation_id"),
            "provider": scene.get("provider"),
            "mission": scene.get("mission"),
            "acquisition_time": acquired.isoformat(),
            "delta_hours": round(delta_h, 3),
            "asset_ref": scene.get("asset_ref"),
            "source_url": scene.get("source_url"),
            "association_status": scene.get("association_status") or "coverage_context",
            "evidence_status": scene.get("evidence_status"),
            "evidence_role": "context_only_pending_review",
        })
    candidates.sort(key=lambda item: item["delta_hours"])
    return candidates[:limit]
