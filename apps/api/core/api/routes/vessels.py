"""
Vessel registry API routes.

GET /api/v1/vessels              - full GeoJSON (cached, fast)
GET /api/v1/vessels?since=<ISO>  - incremental update (only changed vessels)
GET /api/v1/vessels/stats        - counts: total known, positioned, active 30m
GET /api/v1/vessels/nearest      - closest vessels to a distress point
GET /api/v1/vessels/sar-intercept - SAR triangulation for an active alert
"""
from __future__ import annotations

import math
from typing import Optional

import asyncio

from fastapi import APIRouter, Query
from fastapi.responses import Response

router = APIRouter()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _registry_geojson(since: Optional[str] = None) -> dict:
    from core.vessels.registry import registry
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: registry.get_geojson(since=since))


@router.get("/api/v1/vessels")
async def vessel_registry(since: Optional[str] = Query(default=None)):
    import json as _json
    from core.vessels.registry import registry

    loop = asyncio.get_event_loop()

    if since:
        # Incremental poll: return only vessels updated after `since`.
        # The full 9k-vessel dataset is ~4 MB; incremental is typically <50 KB.
        result = await loop.run_in_executor(None, lambda: registry.get_geojson(since=since))
        return Response(content=_json.dumps(result).encode(), media_type="application/json")

    # Full fetch — use pre-serialized cache when fresh.
    cached = registry.get_geojson_json()
    if cached is not None:
        return Response(content=cached, media_type="application/json")

    # Cache miss: rebuild in executor (non-blocking).
    await loop.run_in_executor(None, lambda: registry.get_geojson(since=None))
    cached = registry.get_geojson_json()
    if cached is not None:
        return Response(content=cached, media_type="application/json")

    result = await loop.run_in_executor(None, lambda: registry.get_geojson(since=None))
    return Response(content=_json.dumps(result).encode(), media_type="application/json")


@router.get("/api/v1/vessels/stats")
async def vessel_stats():
    from core.vessels.registry import registry
    from core.vessels.track_store import track_store

    return {**registry.stats(), "track_store": track_store.stats()}


@router.get("/api/v1/vessels/{mmsi}/track")
async def vessel_track(
    mmsi: str,
    hours: float = Query(default=48.0, ge=0.1, le=24 * 90),
    limit: int = Query(default=5000, ge=1, le=50_000),
):
    """AIS position history for one MMSI as a GeoJSON LineString + points."""
    from datetime import datetime, timedelta, timezone

    from core.vessels.track_store import track_store

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    points = track_store.track(mmsi, since=since, limit=limit)
    coords = [[p["lon"], p["lat"]] for p in points]
    features = []
    if len(coords) >= 2:
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"mmsi": mmsi, "points": len(coords)},
        })
    for p in points:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
            "properties": p,
        })
    return {"type": "FeatureCollection", "features": features,
            "meta": {"mmsi": mmsi, "points": len(points), "hours": hours}}


@router.get("/api/v1/vessels/nearest")
async def nearest_vessels(
    lat: float = Query(...),
    lon: float = Query(...),
    limit: int = Query(default=5, ge=1, le=20),
):
    payload = await _registry_geojson()
    nearest: list[dict] = []

    for feature in payload.get("features", []):
        coords = feature.get("geometry", {}).get("coordinates") or []
        if len(coords) != 2:
            continue

        vessel_lon = float(coords[0])
        vessel_lat = float(coords[1])
        props = feature.get("properties", {})
        distance_km = _haversine_km(lat, lon, vessel_lat, vessel_lon)

        nearest.append({
            "mmsi": props.get("mmsi"),
            "ship_name": props.get("ship_name") or props.get("name") or props.get("mmsi"),
            "type": props.get("type") or props.get("ship_type") or "unknown",
            "lat": vessel_lat,
            "lon": vessel_lon,
            "speed": props.get("speed") if props.get("speed") is not None else props.get("sog"),
            "course": props.get("course") if props.get("course") is not None else props.get("cog"),
            "last_seen": props.get("last_seen") or props.get("timestamp_utc"),
            "distance_km": round(distance_km, 2),
            "distance_nm": round(distance_km / 1.852, 2),
        })

    nearest.sort(key=lambda item: item["distance_km"])
    return {
        "query": {"lat": lat, "lon": lon, "limit": limit},
        "count": min(limit, len(nearest)),
        "vessels": nearest[:limit],
    }


def _destination(lat: float, lon: float, bearing_deg: float, distance_nm: float):
    """Rhumb-line destination given start, bearing, distance in nm."""
    R = 3440.065
    d = distance_nm / R
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = lat1 + d * math.cos(br)
    if abs(lat2) > math.pi / 2:
        lat2 = math.copysign(math.pi - abs(lat2), lat2)
    dlon = d * math.sin(br) / math.cos((lat1 + lat2) / 2) if math.cos((lat1 + lat2) / 2) != 0 else 0
    lon2 = lon1 + dlon
    return math.degrees(lat2), math.degrees(lon2)


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2 (degrees true)."""
    la1, lo1, la2, lo2 = map(math.radians, [lat1, lon1, lat2, lon2])
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


@router.get("/api/v1/vessels/sar-intercept")
async def sar_intercept(
    lat: float = Query(..., description="Distress latitude"),
    lon: float = Query(..., description="Distress longitude"),
    drift_speed_ms: float = Query(default=0.5, description="Target drift speed m/s"),
    drift_dir_deg: float = Query(default=0.0, description="Target drift direction (degrees true)"),
    search_radius_nm: float = Query(default=200.0, ge=1.0, le=500.0),
    limit: int = Query(default=15, ge=1, le=50),
):
    """
    SAR intercept triangulation.

    For each vessel within search_radius_nm, computes:
    - distance and bearing to the distress point
    - ETA at current speed
    - predicted target position when the vessel arrives (accounting for drift)
    - intercept score (higher = better candidate)

    NGO / coastguard vessels are boosted in the score.
    """
    from core.vessels.registry import registry
    try:
        from core.intel.ngo_registry import is_ngo, get_ngo_info
        _ngo_available = True
    except Exception:
        _ngo_available = False

    geojson = registry.get_geojson()
    drift_speed_kn = drift_speed_ms * 1.94384  # m/s → knots

    candidates = []
    for feat in geojson.get("features", []):
        coords = (feat.get("geometry") or {}).get("coordinates", [])
        if len(coords) != 2:
            continue
        props = feat.get("properties") or {}
        v_lon, v_lat = float(coords[0]), float(coords[1])
        dist_nm = _haversine_km(lat, lon, v_lat, v_lon) / 1.852

        if dist_nm > search_radius_nm:
            continue

        mmsi = str(props.get("mmsi", ""))
        speed_kn = float(props.get("last_speed") or props.get("speed") or props.get("sog") or 0)
        course_deg = float(props.get("last_course") or props.get("course") or props.get("cog") or 0)
        ngo = _ngo_available and is_ngo(mmsi)
        ngo_info = (get_ngo_info(mmsi) if ngo else None) or {}

        bearing_to_distress = _bearing(v_lat, v_lon, lat, lon)
        effective_speed = max(speed_kn, 0.5)
        eta_h = dist_nm / effective_speed

        # Where will the target be when the vessel arrives?
        drift_nm = drift_speed_kn * eta_h
        intercept_lat, intercept_lon = _destination(lat, lon, drift_dir_deg, drift_nm)
        intercept_dist_nm = _haversine_km(v_lat, v_lon, intercept_lat, intercept_lon) / 1.852
        intercept_bearing = _bearing(v_lat, v_lon, intercept_lat, intercept_lon)

        course_change = min(abs(course_deg - intercept_bearing), 360 - abs(course_deg - intercept_bearing))
        speed_score = min(speed_kn / 10.0, 1.0)
        proximity_score = max(0.0, 1.0 - dist_nm / search_radius_nm)
        heading_score = max(0.0, 1.0 - course_change / 180.0)
        intercept_score = round(
            (proximity_score * 0.4 + heading_score * 0.35 + speed_score * 0.25) * (1.5 if ngo else 1.0),
            3,
        )

        candidates.append({
            "mmsi": mmsi,
            "ship_name": props.get("ship_name") or props.get("name") or mmsi,
            "type": props.get("type") or props.get("ship_type") or "unknown",
            "lat": v_lat,
            "lon": v_lon,
            "speed_kn": round(speed_kn, 1),
            "course_deg": round(course_deg, 1),
            "distance_nm": round(dist_nm, 2),
            "bearing_to_distress_deg": round(bearing_to_distress, 1),
            "eta_h": round(eta_h, 2),
            "intercept_lat": round(intercept_lat, 5),
            "intercept_lon": round(intercept_lon, 5),
            "intercept_bearing_deg": round(intercept_bearing, 1),
            "course_change_deg": round(course_change, 1),
            "intercept_score": intercept_score,
            "is_ngo": ngo,
            "org": ngo_info.get("org", ""),
            "role": ngo_info.get("role", ""),
        })

    candidates.sort(key=lambda c: -c["intercept_score"])
    return {
        "distress": {"lat": lat, "lon": lon},
        "drift": {"speed_ms": drift_speed_ms, "dir_deg": drift_dir_deg},
        "search_radius_nm": search_radius_nm,
        "count": min(limit, len(candidates)),
        "candidates": candidates[:limit],
    }
