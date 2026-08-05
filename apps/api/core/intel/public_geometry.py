# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared geometry + location-precision projection for the public feed.

Used by both core/api/routes/live.py (the VM-hosted REST/WS feed) and
core/live_edge_publisher.py (the Cloudflare edge push) so a report's
area-vs-point representation, and its precision label, can never silently
diverge between the two paths. thread_reposts/repost_count reaching one
path and not the other (both hand-maintained the same projection logic
separately) is exactly the bug class this exists to stop repeating.
"""
from __future__ import annotations

from typing import Optional

from core.intel.store import IntelEvent


def public_geometry_and_precision(event: IntelEvent) -> tuple[Optional[dict], str]:
    """(geojson_geometry, location_precision) for the public feed.

    A stored area_geojson (see core.intel.area_extract) always wins over
    the plain lat/lon fallback -- the polygon is more information than the
    single point derived alongside it (event.lat/lon hold the polygon's own
    centroid, kept only for anything that still needs a single reference
    point, e.g. distance sorting).
    """
    area = event.metadata.get("area_geojson")
    if area:
        confidence = str(event.metadata.get("area_confidence") or "area")
        return area, confidence

    if event.lat is None or event.lon is None:
        return None, "unpositioned"

    coordinate_source = str(event.metadata.get("coordinate_source") or "")
    precision = (
        "regional_centroid" if coordinate_source == "place_centroid"
        else "reported_or_derived"
    )
    return {"type": "Point", "coordinates": [event.lon, event.lat]}, precision
