"""
Chokepoint monitor — counts vessels currently transiting strategic straits.
"""
from __future__ import annotations
from typing import Any

CHOKEPOINTS = [
    {
        "id": "hormuz",
        "name": "Strait of Hormuz",
        "lat": 26.6, "lon": 56.5,
        "bbox": {"min_lat": 25.5, "max_lat": 27.5, "min_lon": 55.5, "max_lon": 59.0},
        "zoom": 8,
        "description": "Iran / UAE·Oman — oil transit choke",
    },
    {
        "id": "suez",
        "name": "Suez Canal",
        "lat": 30.5, "lon": 32.35,
        "bbox": {"min_lat": 29.5, "max_lat": 32.5, "min_lon": 32.0, "max_lon": 33.0},
        "zoom": 9,
        "description": "Egypt — Atlantic–Indo-Pacific shortcut",
    },
    {
        "id": "bab_mandeb",
        "name": "Bab el-Mandeb",
        "lat": 12.6, "lon": 43.4,
        "bbox": {"min_lat": 11.5, "max_lat": 13.5, "min_lon": 42.5, "max_lon": 44.5},
        "zoom": 9,
        "description": "Yemen / Djibouti — Red Sea gateway",
    },
    {
        "id": "gibraltar",
        "name": "Strait of Gibraltar",
        "lat": 35.95, "lon": -5.5,
        "bbox": {"min_lat": 35.5, "max_lat": 36.5, "min_lon": -6.5, "max_lon": -4.5},
        "zoom": 9,
        "description": "Spain / Morocco — Atlantic–Med gateway",
    },
    {
        "id": "sicily",
        "name": "Sicily Channel",
        "lat": 37.1, "lon": 11.8,
        "bbox": {"min_lat": 36.0, "max_lat": 38.5, "min_lon": 10.5, "max_lon": 13.5},
        "zoom": 8,
        "description": "Italy / Tunisia — central Med divider",
    },
    {
        "id": "messina",
        "name": "Strait of Messina",
        "lat": 38.15, "lon": 15.55,
        "bbox": {"min_lat": 37.8, "max_lat": 38.5, "min_lon": 15.2, "max_lon": 16.0},
        "zoom": 10,
        "description": "Italy mainland / Sicily",
    },
]


def _in_bbox(lat: float, lon: float, bbox: dict) -> bool:
    return (
        bbox["min_lat"] <= lat <= bbox["max_lat"]
        and bbox["min_lon"] <= lon <= bbox["max_lon"]
    )


def count_vessels_at_chokepoints(geojson_features: list[dict]) -> list[dict[str, Any]]:
    """
    Given a list of GeoJSON features (vessels with lat/lon in geometry.coordinates),
    returns chokepoint list enriched with vessel_count and vessel_ids.
    """
    result = []
    for cp in CHOKEPOINTS:
        vessels_in = []
        for feat in geojson_features:
            coords = feat.get("geometry", {}).get("coordinates")
            if not coords or len(coords) < 2:
                continue
            lon_v, lat_v = coords[0], coords[1]
            if _in_bbox(lat_v, lon_v, cp["bbox"]):
                vessels_in.append(feat.get("properties", {}).get("vessel_id", "?"))
        result.append({
            **cp,
            "vessel_count": len(vessels_in),
            "vessel_ids": vessels_in[:10],  # first 10 for display
        })
    return result
