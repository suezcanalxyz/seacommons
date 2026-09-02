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
from core.intel.location_evidence import COARSE_COORDINATE_SOURCES
from core.intel.store import IntelEvent


def public_geometry_and_precision(event: IntelEvent) -> tuple[dict | None, str]:
    """(geojson_geometry, location_precision) for the public feed.

    A stored area_geojson (see core.intel.area_extract) wins over the plain
    lat/lon fallback *only while the coordinate is coarse* -- a named-region
    search polygon is more information than its own centroid.

    Once the event carries a real extracted position (an OCR'd map
    coordinate, a drop-pin fit, a coordinate read out of the post text), that
    point is the better information and must be shown, even if a now-stale
    area_geojson is still attached to the row: a lingering hashtag-derived
    polygon otherwise keeps hiding the actual location an Alarm Phone map
    screenshot contained (real prod bug -- events with a correct
    ``media_ocr_text`` coordinate rendered as a fuzzy "Central Med" region).
    """
    area = event.metadata.get("area_geojson")
    coordinate_source = str(event.metadata.get("coordinate_source") or "").lower()
    coordinate_is_coarse = coordinate_source in COARSE_COORDINATE_SOURCES
    if area and (coordinate_is_coarse or event.lat is None or event.lon is None):
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
    snapped_lat, snapped_lon = landmask.nearest_sea_point(lat, lon)
    if landmask.is_on_land(snapped_lat, snapped_lon) is True:
        # nearest_sea_point searches only a bounded radius and gives up
        # rather than snapping a real inland report onto an unrelated
        # coastline far away. A report that is still on land after that is
        # a genuinely land-based incident (e.g. an Evros river/border
        # pushback, which Alarm Phone reports alongside sea rescues).
        hct = str(event.metadata.get("humanitarian_case_type") or "").lower()
        if hct == "land_humanitarian":
            # Product policy §1 / §11-B: a land Alarm Phone incident stays
            # visible. It is shown at its reported (un-snapped) coordinate as
            # a land humanitarian point -- red, no maritime drift -- never
            # removed and never nudged to sea. Land is a visibility
            # condition, not a reason to delete the humanitarian event.
            return (
                {"type": "Point", "coordinates": [lon, lat]},
                LocationPrecision.APPROXIMATE.value,
            )
        # For a maritime case, a coordinate still on land after the snap is a
        # bad extraction (a stray number pair, an OCR misread). Plotting a
        # "boat at sea" marker there is false; drop it.
        return None, LocationPrecision.UNPOSITIONED.value
    lat, lon = snapped_lat, snapped_lon

    if coordinate_source == "place_centroid":
        precision = LocationPrecision.REGIONAL_CENTROID.value
    elif coordinate_source == "region_area":
        # The point here is the centroid of a named-region search area. If a
        # polygon is attached it was already returned above; reaching here
        # means it was lost upstream -- fail safe and never present a region
        # centroid as a reported position.
        precision = LocationPrecision.APPROXIMATE.value
    else:
        precision = LocationPrecision.REPORTED_OR_DERIVED.value
    return {"type": "Point", "coordinates": [lon, lat]}, precision
