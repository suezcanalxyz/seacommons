# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared geometry + location-precision projection for the public feed.

Used by both core/live/projection.py (the VM-hosted REST/WS feed) and
core/live_edge_publisher.py (the Cloudflare edge push) so a report's
area-vs-point representation, and its precision label, can never silently
diverge between the two paths. thread_reposts/repost_count reaching one
path and not the other (both hand-maintained the same projection logic
separately) is exactly the bug class this exists to stop repeating.
"""

from __future__ import annotations

from core.domain.live_contracts import LocationPrecision
from core.intel import landmask
from core.intel.store import IntelEvent


def public_geometry_and_precision(event: IntelEvent) -> tuple[dict | None, str]:
    """(geojson_geometry, location_precision) for the public feed.

    A stored area_geojson (see core.intel.area_extract) always wins over
    the plain lat/lon fallback -- the polygon is more information than the
    single point derived alongside it (event.lat/lon hold the polygon's own
    centroid, kept only for anything that still needs a single reference
    point, e.g. distance sorting).
    """
    area = event.metadata.get("area_geojson")
    if area:
        confidence = str(event.metadata.get("area_confidence") or LocationPrecision.AREA)
        try:
            precision = LocationPrecision(confidence).value
        except ValueError:
            precision = LocationPrecision.AREA.value
        return area, precision

    if event.lat is None or event.lon is None:
        return None, LocationPrecision.UNPOSITIONED.value

    lat, lon = float(event.lat), float(event.lon)

    # A coordinate outside the area SeaCommons covers is a bad extraction (a
    # stray number pair from tweet text, an OCR misread). Do not plot it.
    if not landmask.in_operational_region(lat, lon):
        return None, LocationPrecision.UNPOSITIONED.value

    # Every plotted location is a boat — it must be at sea. A gazetteer
    # centroid, a relative offset or a drop-pin reading can legitimately land
    # on a coastline even though the report is unambiguously offshore; nudge it
    # onto the nearest water. No-op when the point is already at sea or the
    # landmask is unavailable.
    lat, lon = landmask.nearest_sea_point(lat, lon)
    if landmask.is_on_land(lat, lon) is True:
        # nearest_sea_point searches only a bounded radius and gives up
        # rather than snapping a real inland report onto an unrelated
        # coastline far away. A report that is still on land after that is
        # not a vessel whose pin needs nudging -- it is a genuinely
        # land-based incident (e.g. an Evros river/border pushback, which
        # Alarm Phone reports alongside sea rescues). This model has no
        # honest way to represent that as a boat position; plotting one
        # anyway is a false "boat at sea" marker. Drop it instead of
        # fabricating a location.
        return None, LocationPrecision.UNPOSITIONED.value

    coordinate_source = str(event.metadata.get("coordinate_source") or "")
    if coordinate_source == "place_centroid":
        precision = LocationPrecision.REGIONAL_CENTROID.value
    elif coordinate_source == "region_area":
        # The point here is the centroid of a named-region search area; the
        # polygon (handled above) is the real geometry. Reaching this branch
        # means the polygon was lost somewhere upstream -- fail safe and never
        # present a region centroid as a reported position.
        precision = LocationPrecision.APPROXIMATE.value
    else:
        precision = LocationPrecision.REPORTED_OR_DERIVED.value
    return {"type": "Point", "coordinates": [lon, lat]}, precision
