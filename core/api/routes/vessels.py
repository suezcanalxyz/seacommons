"""
Vessel registry API routes.

GET /api/v1/vessels              — full GeoJSON (cached, fast)
GET /api/v1/vessels?since=<ISO>  — incremental update (only changed vessels)
GET /api/v1/vessels/stats        — counts: total known, positioned, active 30m
"""
from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter()


@router.get("/api/v1/vessels")
async def vessel_registry(since: Optional[str] = Query(default=None)):
    from core.vessels.registry import registry
    return registry.get_geojson(since=since)


@router.get("/api/v1/vessels/stats")
async def vessel_stats():
    from core.vessels.registry import registry
    return registry.stats()
