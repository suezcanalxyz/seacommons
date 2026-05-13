# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Maritime operational zones — SAR regions, chokepoints, and hotspot polygons.

GET /api/v1/zones              — GeoJSON FeatureCollection of SAR zones
GET /api/v1/zones/classify     — Classify a point + trajectory (legal/SAR analysis)
GET /api/v1/zones/platforms    — Mediterranean oil/gas platforms GeoJSON
GET /api/v1/chokepoints        — vessel counts at strategic straits
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter()

# ── Mediterranean oil/gas platforms (public data, EMODnet / OGA / OSM) ────────
# Format: [lon, lat, name, country, operator, type]
_OIL_PLATFORMS = [
    # Italy (Adriatic and Sicilian Channel)
    [12.8833, 44.4333, "Cervia", "Italy", "ENI", "gas"],
    [12.9667, 44.2500, "Barbara", "Italy", "ENI", "gas"],
    [13.1000, 43.9167, "Porto Corsini", "Italy", "ENI", "gas"],
    [13.5833, 44.1667, "Naomi", "Italy", "ENI", "gas"],
    [13.7667, 44.0333, "Pandora", "Italy", "ENI", "gas"],
    [14.2000, 43.4167, "Annamaria", "Italy", "ENI", "gas"],
    [15.5000, 42.0000, "Vega", "Italy", "ENI", "oil"],
    [12.5667, 37.8167, "Perla", "Italy", "ENI", "gas"],
    [13.0000, 37.5000, "Argo", "Italy", "ENI", "oil"],
    # Libya
    [13.2833, 32.8833, "Bouri", "Libya", "NOC/ENI", "oil"],
    [12.9167, 33.0500, "Bouri NW", "Libya", "NOC", "oil"],
    # Tunisia
    [9.4500, 37.5500, "Ashtart", "Tunisia", "ETAP", "oil"],
    [11.0000, 35.5000, "Miskar", "Tunisia", "BG Group", "gas"],
    [9.8333, 36.9167, "Cercina", "Tunisia", "ETAP", "oil"],
    # Egypt (western Med / offshore)
    [28.6667, 31.5667, "Zohr", "Egypt", "ENI", "gas"],
    [28.0000, 31.0000, "Nooros", "Egypt", "ENI", "gas"],
    # Greece
    [26.5167, 38.3333, "Prinos", "Greece", "Energean", "oil"],
    [26.4000, 38.4000, "Prinos North", "Greece", "Energean", "oil"],
    [23.5833, 38.0833, "Epsilon", "Greece", "Energean", "oil"],
    # Cyprus (EEZ)
    [33.5833, 34.2500, "Aphrodite", "Cyprus", "Noble/Shell", "gas"],
    [33.0000, 34.0833, "Calypso", "Cyprus", "ENI", "gas"],
    # Spain (Mediterranean)
    [0.9167, 40.5167, "Amposta", "Spain", "Repsol", "oil"],
    [1.5000, 40.5000, "Casablanca", "Spain", "Repsol", "oil"],
    # Algeria
    [8.5667, 37.3167, "Skikda offshore", "Algeria", "Sonatrach", "gas"],
    # Croatia (Adriatic)
    [15.1667, 45.1667, "Ivana", "Croatia", "INA", "gas"],
    [14.9167, 45.0833, "Annamaria A", "Croatia", "INA", "gas"],
    # Israel / Lebanon
    [33.8667, 31.6667, "Leviathan", "Israel", "Chevron", "gas"],
    [34.6667, 32.4167, "Tamar", "Israel", "Chevron", "gas"],
    [34.6000, 32.6167, "Dalit", "Israel", "Delek", "gas"],
]

router = APIRouter()

# SAR regions are approximations based on public IMO/MRCC documentation.
# Official SRR boundaries are filed with IMO GISIS and may differ.
# All coordinates: [longitude, latitude]
_SAR_ZONES = [
    {
        "id": "med_central_hotspot",
        "name": "Central Med SAR Hotspot",
        "zone_type": "hotspot",
        "description": "Primary migration route — highest SAR incident density in the Mediterranean",
        "polygon": [
            [11.0, 33.0], [16.5, 33.0], [16.5, 35.8],
            [14.5, 36.2], [12.5, 36.2], [11.0, 35.2], [11.0, 33.0],
        ],
        "mrcc": "MRCC Roma (+39 06 59 08 04) / JRCC Malta (+356 21 238797)",
        "color": "#ef4444",
        "fill_opacity": 0.07,
        "stroke_opacity": 0.55,
    },
    {
        "id": "italy_srr_south",
        "name": "Italian SRR — southern sector",
        "zone_type": "srr",
        "description": "MRCC Roma — Italian Search and Rescue Region, southern portion",
        "polygon": [
            [6.5, 37.5], [18.5, 37.5], [18.5, 35.0],
            [15.5, 33.0], [11.5, 33.0], [6.5, 35.5], [6.5, 37.5],
        ],
        "mrcc": "MRCC Roma: +39 06 59 08 04",
        "color": "#3b82f6",
        "fill_opacity": 0.04,
        "stroke_opacity": 0.4,
    },
    {
        "id": "malta_srr",
        "name": "Maltese SRR",
        "zone_type": "srr",
        "description": "JRCC Malta — Malta Search and Rescue Region",
        "polygon": [
            [12.0, 36.5], [17.5, 36.5], [17.5, 32.5],
            [12.0, 32.5], [12.0, 36.5],
        ],
        "mrcc": "JRCC Malta: +356 21 238797",
        "color": "#f59e0b",
        "fill_opacity": 0.04,
        "stroke_opacity": 0.35,
    },
    {
        "id": "libyan_declared_zone",
        "name": "Libyan declared zone",
        "zone_type": "declared",
        "description": "Libya-declared maritime zone (2018) — disputed, overlaps Maltese and Italian SRR. "
                       "Do NOT rely on MRCC Tripoli for SAR coordination.",
        "polygon": [
            [11.0, 33.5], [25.0, 33.5], [25.0, 29.5],
            [11.0, 29.5], [11.0, 33.5],
        ],
        "mrcc": "MRCC Tripoli (unreliable for SAR operations)",
        "color": "#f97316",
        "fill_opacity": 0.04,
        "stroke_opacity": 0.3,
    },
    {
        "id": "tunisia_srr",
        "name": "Tunisian SRR",
        "zone_type": "srr",
        "description": "MRCC Tunis — Tunisia Search and Rescue Region",
        "polygon": [
            [8.0, 38.5], [12.5, 38.5], [12.5, 35.5],
            [8.0, 35.5], [8.0, 38.5],
        ],
        "mrcc": "MRCC Tunis: +216 71 735 004",
        "color": "#22c55e",
        "fill_opacity": 0.04,
        "stroke_opacity": 0.35,
    },
]


@router.get("/api/v1/zones")
async def get_zones():
    """Return SAR zones and operational hotspots as GeoJSON."""
    features = []
    for zone in _SAR_ZONES:
        coords = zone["polygon"]
        # GeoJSON polygon ring must be closed
        ring = coords if coords[0] == coords[-1] else coords + [coords[0]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "id": zone["id"],
                "name": zone["name"],
                "zone_type": zone["zone_type"],
                "description": zone["description"],
                "mrcc": zone["mrcc"],
                "color": zone["color"],
                "fill_opacity": zone["fill_opacity"],
                "stroke_opacity": zone["stroke_opacity"],
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "note": "Boundaries are approximations for operational awareness. "
                    "Official SRR limits filed with IMO GISIS.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/api/v1/chokepoints")
async def get_chokepoints():
    """Return strategic strait list with live vessel counts from registry."""
    from core.vessels.registry import registry
    from core.chokepoints.monitor import count_vessels_at_chokepoints

    geojson = registry.get_geojson()
    counts = count_vessels_at_chokepoints(geojson.get("features", []))
    return {
        "chokepoints": counts,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/v1/zones/classify")
async def classify_zone(
    lat: float = Query(..., description="Origin latitude"),
    lon: float = Query(..., description="Origin longitude"),
    vessel_type: str = Query("rubber_boat"),
    persons: int = Query(30, ge=1),
    duration_h: float = Query(24.0, ge=1),
    traj: Optional[str] = Query(None, description="Trajectory as JSON array [[lon,lat],...]"),
    weather_wave: Optional[float] = Query(None),
    weather_wind: Optional[float] = Query(None),
):
    """
    Classify SAR zones, compute legal framework, survival estimate for a drift origin.
    If `traj` is provided (JSON-encoded list of [lon,lat] pairs), the full trajectory
    is analysed for multi-zone intersection.
    """
    import json
    from core.zones.classifier import drift_analysis

    traj_coords: Optional[list] = None
    if traj:
        try:
            traj_coords = json.loads(traj)
        except Exception:
            traj_coords = None

    weather = {}
    if weather_wave is not None:
        weather["waves"] = {"significant_height_m": weather_wave}
    if weather_wind is not None:
        weather["wind"] = {"speed_ms": weather_wind}

    return drift_analysis(
        lat=lat, lon=lon,
        trajectory_coords=traj_coords,
        vessel_type=vessel_type,
        persons=persons,
        duration_h=duration_h,
        weather=weather or None,
    )


@router.get("/api/v1/zones/platforms")
async def get_platforms():
    """
    Mediterranean oil and gas platform positions as GeoJSON.
    Source: EMODnet, OGA, OpenStreetMap (public data).
    """
    features = []
    for p in _OIL_PLATFORMS:
        lon, lat, name, country, operator, ptype = p
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": name,
                "country": country,
                "operator": operator,
                "platform_type": ptype,
                "icon": "platform",
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "count": len(features),
            "note": "Approximate positions — verify with official navigation charts.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
