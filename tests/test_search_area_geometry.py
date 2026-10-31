"""Regression tests for safe, shared projection of stored search areas."""
import math

import pytest

from core.intel.macro_drift import spatial_prior_for_event
from core.intel.public_geometry import public_geometry_and_precision
from core.intel.search_area_geometry import valid_search_area_geometry
from core.intel.store import IntelEvent


VALID = {"type": "Polygon", "coordinates": [
    [[12.0, 34.0], [13.0, 34.0], [12.0, 35.0], [12.0, 34.0]],
]}


@pytest.mark.parametrize("geometry", [
    None,
    {},
    {"type": "Point", "coordinates": [12, 34]},
    {"type": "Polygon", "coordinates": []},
    {"type": "Polygon", "coordinates": {}},
    {"type": "Polygon", "coordinates": [[[12, 34], [13, 34], [12, 35]]]},
    {"type": "Polygon", "coordinates": [[[12, 34], [13, 34], [12, 35], [13, 35]]]},
    {"type": "Polygon", "coordinates": [[[12, 34], [12, 34], [12, 34], [12, 34]]]},
    {"type": "Polygon", "coordinates": [[[181, 34], [13, 34], [12, 35], [181, 34]]]},
    {"type": "Polygon", "coordinates": [[[12, 91], [13, 34], [12, 35], [12, 91]]]},
    {"type": "Polygon", "coordinates": [[[math.nan, 34], [13, 34], [12, 35], [math.nan, 34]]]},
    {"type": "Polygon", "coordinates": [[[math.inf, 34], [13, 34], [12, 35], [math.inf, 34]]]},
    {"type": "Polygon", "coordinates": [[[10 ** 400, 34], [13, 34], [12, 35], [10 ** 400, 34]]]},
    {"type": "Polygon", "coordinates": [[[True, 34], [13, 34], [12, 35], [True, 34]]]},
    {"type": "Polygon", "coordinates": [[["12", 34], [13, 34], [12, 35], ["12", 34]]]},
    {"type": "Polygon", "coordinates": [[[12, 34, "bad"], [13, 34], [12, 35], [12, 34]]]},
    {"type": "Polygon", "coordinates": [[[12, 34], [13, 34], [12, 35], [12, 34, 1]]]},
    {"type": "MultiPolygon", "coordinates": [VALID["coordinates"], []]},
    {"type": "MultiPolygon", "coordinates": [[[[12, 34], [13, 34], [12, 35]]]]},
    {"type": "Polygon", "coordinates": [[[12, 34], [13, 34], [12, 35], [12, 34]], []]},
    {"type": "Polygon", "coordinates": [[[]] * 4]},
    {"type": "Polygon", "coordinates": [[(12, 34), (13, 34), (12, 35), (12, 34)]]},
    {"type": "Polygon", "coordinates": [[
        [12.0 + (i % 3) * 0.01, 34.0] for i in range(10_002)
    ]]},
])
def test_reject_invalid_stored_area_geometry(geometry):
    assert valid_search_area_geometry(geometry) is False


@pytest.mark.parametrize("geometry", [
    VALID,
    {"type": "MultiPolygon", "coordinates": [VALID["coordinates"], VALID["coordinates"]]},
    {"type": "Polygon", "coordinates": [[
        [12.0, 34.0, 0.0], [13.0, 34.0, 0.0],
        [12.0, 35.0, 0.0], [12.0, 34.0, 0.0],
    ]]},
])
def test_accept_valid_polygon_and_multipolygon(geometry):
    assert valid_search_area_geometry(geometry) is True


def test_macro_prior_does_not_publish_invalid_geojson():
    malformed = {"type": "Polygon", "coordinates": [[[181, 34], [13, 34], [12, 35], [181, 34]]]}
    event = IntelEvent(
        source="alarm_phone", type="twitter", title="Distress near Lampedusa",
        metadata={"is_distress": True, "area_geojson": malformed},
    )
    prior = spatial_prior_for_event(event)
    assert prior["candidate"] is True
    assert prior["geometry"] is None
    assert prior["location_evidence"] == "no_geographic_area_resolved"
    assert prior["physical_drift_computed"] is False


def test_public_projection_does_not_publish_invalid_geojson():
    malformed = {"type": "Polygon", "coordinates": [[[181, 34], [13, 34], [12, 35], [181, 34]]]}
    event = IntelEvent(
        source="alarm_phone", type="twitter", title="Distress near Lampedusa",
        lat=None, lon=None,
        metadata={"coordinate_source": "region_area", "area_geojson": malformed},
    )
    geometry, precision = public_geometry_and_precision(event)
    assert geometry is None
    assert precision == "unpositioned"


def test_public_projection_preserves_valid_area():
    event = IntelEvent(
        source="alarm_phone", type="twitter", title="Distress near Lampedusa",
        lat=None, lon=None,
        metadata={"coordinate_source": "region_area", "area_geojson": VALID},
    )
    geometry, precision = public_geometry_and_precision(event)
    assert geometry == VALID
    assert precision == "area"
