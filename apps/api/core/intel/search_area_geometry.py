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


def _finite_number(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def valid_search_area_geometry(value: Any) -> bool:
    """Accept bounded, closed Polygon/MultiPolygon with finite lon/lat pairs."""
    if not isinstance(value, dict) or value.get("type") not in {"Polygon", "MultiPolygon"}:
        return False
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, (list, tuple)) or not coordinates:
        return False
    polygons = [coordinates] if value["type"] == "Polygon" else coordinates
    if len(polygons) > _MAX_POLYGONS:
        return False
    vertices = 0
    for polygon in polygons:
        if not isinstance(polygon, (list, tuple)) or not polygon or len(polygon) > _MAX_RINGS:
            return False
        for ring in polygon:
            if not isinstance(ring, (list, tuple)) or len(ring) < 4:
                return False
            vertices += len(ring)
            if vertices > _MAX_VERTICES:
                return False
            points: list[tuple[float, float]] = []
            ring_dimension = len(ring[0]) if isinstance(ring[0], (list, tuple)) else 0
            for position in ring:
                if not isinstance(position, (list, tuple)) or len(position) not in (2, 3) or len(position) != ring_dimension:
                    return False
                if any(not _finite_number(number) for number in position):
                    return False
                lon, lat = position[:2]
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    return False
                points.append((float(lon), float(lat)))
            # GeoJSON linear rings must close on the entire position, not
            # merely longitude/latitude: a 3D start/end altitude mismatch is
            # not a closed ring. Reject repeated interior vertices too; these
            # create zero-length edges or self-touching search boundaries.
            if tuple(ring[0]) != tuple(ring[-1]):
                return False
            unique_vertices = set(points[:-1])
            if len(unique_vertices) < 3 or len(unique_vertices) != len(points) - 1:
                return False
            # Distinct vertices alone do not guarantee an actual search area:
            # collinear and some self-crossing closed rings enclose zero signed
            # area. Subtract the first point for numerical stability.
            x0, y0 = points[0]
            twice_area = math.fsum(
                (points[i][0] - x0) * (points[i + 1][1] - y0)
                - (points[i + 1][0] - x0) * (points[i][1] - y0)
                for i in range(len(points) - 1)
            )
            if twice_area == 0.0:
                return False
    return True
