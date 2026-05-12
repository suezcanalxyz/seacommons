# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Maritime operational zones — SAR regions, chokepoints, and hotspot polygons.

GET /api/v1/zones         — GeoJSON FeatureCollection of SAR zones
GET /api/v1/chokepoints   — vessel counts at strategic straits
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

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
