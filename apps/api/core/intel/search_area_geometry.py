# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed structural validation of persisted WGS84 search-area GeoJSON.

Use at both public geometry projection and macro-drift triage. This validates
shape and numeric bounds, not polygon topology or location evidence.
"""
from __future__ import annotations

import math
from typing import Any

_MAX_POLYGONS = 256
_MAX_RINGS = 256
_MAX_VERTICES = 10_000


def valid_search_area_geometry(value: Any) -> bool:
    """Accept bounded, closed Polygon/MultiPolygon with finite lon/lat pairs."""
    if not isinstance(value, dict) or value.get("type") not in {"Polygon", "MultiPolygon"}:
        return False
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        return False
    polygons = [coordinates] if value["type"] == "Polygon" else coordinates
    if len(polygons) > _MAX_POLYGONS:
        return False
    vertices = 0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon or len(polygon) > _MAX_RINGS:
            return False
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                return False
            vertices += len(ring)
            if vertices > _MAX_VERTICES:
                return False
            points: list[tuple[float, float]] = []
            for position in ring:
                if not isinstance(position, list) or len(position) not in (2, 3):
                    return False
                if any(
                    isinstance(number, bool)
                    or not isinstance(number, (int, float))
                    or not math.isfinite(number)
                    for number in position
                ):
                    return False
                lon, lat = position[:2]
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    return False
                points.append((float(lon), float(lat)))
            if points[0] != points[-1] or len(set(points[:-1])) < 3:
                return False
    return True
