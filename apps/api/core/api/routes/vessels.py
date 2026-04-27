"""
Vessel registry API routes.

GET /api/v1/vessels              - full GeoJSON (cached, fast)
GET /api/v1/vessels?since=<ISO>  - incremental update (only changed vessels)
GET /api/v1/vessels/stats        - counts: total known, positioned, active 30m
GET /api/v1/vessels/nearest      - closest vessels to a distress point
"""
from __future__ import annotations

import math
import os
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter()

_MOCK = os.getenv("MOCK", "false").lower() in ("1", "true", "yes")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _registry_or_mock_geojson(since: Optional[str] = None) -> dict:
    from core.vessels.registry import registry

    payload = registry.get_geojson(since=since)
    if payload.get("features") or not _MOCK:
        return payload

    from core.api.routes.weather import mock_ais_vessels

    return await mock_ais_vessels()


@router.get("/api/v1/vessels")
async def vessel_registry(since: Optional[str] = Query(default=None)):
    return await _registry_or_mock_geojson(since=since)


@router.get("/api/v1/vessels/stats")
async def vessel_stats():
    from core.vessels.registry import registry

    return registry.stats()


@router.get("/api/v1/vessels/nearest")
async def nearest_vessels(
    lat: float = Query(...),
    lon: float = Query(...),
    limit: int = Query(default=5, ge=1, le=20),
):
    payload = await _registry_or_mock_geojson()
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
