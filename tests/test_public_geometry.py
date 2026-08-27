# SPDX-License-Identifier: AGPL-3.0-or-later
"""Precision labelling for the public feed geometry projection."""
from __future__ import annotations

from core.intel.public_geometry import public_geometry_and_precision
from core.intel.store import IntelEvent


def _event(**metadata) -> IntelEvent:
    return IntelEvent(
        id="evt-geo",
        type="twitter",
        severity="high",
        title="Boat in distress",
        source="alarm_phone",
        lat=35.5,
        lon=14.0,
        metadata=metadata,
    )


def test_area_geojson_wins_and_carries_its_confidence() -> None:
    polygon = {"type": "Polygon", "coordinates": [[[14.0, 35.0], [14.2, 35.0], [14.1, 35.2], [14.0, 35.0]]]}
    geom, precision = public_geometry_and_precision(
        _event(coordinate_source="region_area", area_geojson=polygon, area_confidence="area_low_confidence")
    )
    assert geom == polygon
    assert precision == "area_low_confidence"


def test_missing_coordinates_stay_unpositioned() -> None:
    event = _event(coordinate_source="none")
    event.lat = None
    event.lon = None
    geom, precision = public_geometry_and_precision(event)
    assert geom is None
    assert precision == "unpositioned"


def test_place_centroid_is_labelled_regional_centroid() -> None:
    _geom, precision = public_geometry_and_precision(_event(coordinate_source="place_centroid"))
    assert precision == "regional_centroid"


def test_region_area_point_without_polygon_never_reads_as_reported() -> None:
    # A region_area point is the centroid of a named search area. If the
    # polygon was lost upstream we must not present the bare centroid as a
    # reported position (this showed a "boat in the Malta SAR zone" report as
    # a pinpoint next to Malta on the live map).
    geom, precision = public_geometry_and_precision(_event(coordinate_source="region_area"))
    assert geom == {"type": "Point", "coordinates": [14.0, 35.5]}
    assert precision == "approximate"


def test_reported_point_keeps_reported_or_derived() -> None:
    _geom, precision = public_geometry_and_precision(_event(coordinate_source="post_text"))
    assert precision == "reported_or_derived"
