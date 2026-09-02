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


def test_extracted_point_beats_a_stale_area_polygon() -> None:
    # Real production bug: an Alarm Phone map screenshot whose printed
    # coordinate OCR read correctly (media_ocr_text) still rendered as a
    # fuzzy hashtag-derived "Central Med" polygon, because a leftover
    # area_geojson from the pre-OCR bare-place fallback kept winning. Once a
    # real position exists it must be shown; the polygon no longer wins.
    polygon = {
        "type": "Polygon",
        "coordinates": [[[14.0, 35.0], [25.0, 35.0], [25.0, 36.0], [14.0, 35.0]]],
    }
    event = _event(
        coordinate_source="media_ocr_text",
        coordinate_review_status="machine_ocr_unverified",
        location_uncertainty_m=1500,
        area_geojson=polygon,
        area_confidence="area_low_confidence",
    )
    event.lat, event.lon = 34.271533, 11.9423
    geom, precision = public_geometry_and_precision(event)
    assert geom == {"type": "Point", "coordinates": [11.9423, 34.271533]}
    assert precision == "reported_or_derived"


def test_stale_area_still_shown_while_the_coordinate_is_only_a_region() -> None:
    # The polygon must keep winning for a genuinely coarse coordinate --
    # its lat/lon is just the polygon's own centroid.
    polygon = {
        "type": "Polygon",
        "coordinates": [[[14.0, 35.0], [15.0, 35.0], [15.0, 36.0], [14.0, 35.0]]],
    }
    geom, precision = public_geometry_and_precision(
        _event(coordinate_source="region_area", area_geojson=polygon)
    )
    assert geom == polygon
    assert precision == "area"


def test_area_polygon_is_the_fallback_when_the_extracted_point_is_missing() -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [[[14.0, 35.0], [15.0, 35.0], [15.0, 36.0], [14.0, 35.0]]],
    }
    event = _event(coordinate_source="media_ocr_text", area_geojson=polygon)
    event.lat = None
    event.lon = None
    geom, _precision = public_geometry_and_precision(event)
    assert geom == polygon


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


def test_point_outside_the_operational_region_is_dropped() -> None:
    # A stray number pair parsed out of unrelated tweet text (real prod case:
    # a text-only tweet about activists in Cote d'Ivoire yielded -7, 44 in the
    # Indian Ocean) must never be plotted as a distress position.
    event = _event(coordinate_source="post_text")
    event.lat, event.lon = -7.0, 44.0
    geom, precision = public_geometry_and_precision(event)
    assert geom is None
    assert precision == "unpositioned"


def test_land_point_too_far_from_sea_to_snap_is_dropped(monkeypatch) -> None:
    # Regression: a genuinely land-based report (e.g. an Evros river/border
    # pushback -- Alarm Phone reports those alongside sea rescues) is more
    # than nearest_sea_point's bounded search radius from open water. It
    # gives up and returns the point unchanged (logged, not raised) rather
    # than snapping it onto an unrelated coastline far away. Observed live:
    # a report at 41.55, 26.53 (deep inland Thrace) plotted exactly there as
    # a "boat" marker. That must be dropped, not shown as a false position.
    monkeypatch.setattr("core.intel.landmask.is_on_land", lambda lat, lon: True)
    monkeypatch.setattr("core.intel.landmask.nearest_sea_point", lambda lat, lon: (lat, lon))
    event = _event(coordinate_source="post_text")
    event.lat, event.lon = 41.55253, 26.52697
    geom, precision = public_geometry_and_precision(event)
    assert geom is None
    assert precision == "unpositioned"


def test_land_humanitarian_alarm_phone_point_stays_visible(monkeypatch) -> None:
    # Product policy §1 / §11-B: a land Alarm Phone incident (Evros border,
    # detention, pushback on land) is NOT removed just because it is on land.
    # It is shown at its reported coordinate as a land humanitarian point --
    # red, no maritime drift. (drift eligibility is blocked separately.)
    monkeypatch.setattr("core.intel.landmask.is_on_land", lambda lat, lon: True)
    monkeypatch.setattr("core.intel.landmask.nearest_sea_point", lambda lat, lon: (lat, lon))
    event = _event(coordinate_source="post_text", humanitarian_case_type="land_humanitarian")
    event.lat, event.lon = 41.55253, 26.52697
    geom, precision = public_geometry_and_precision(event)
    assert geom == {"type": "Point", "coordinates": [26.52697, 41.55253]}
    assert precision == "approximate"


def test_on_land_point_is_snapped_to_water(monkeypatch) -> None:
    # Every plotted location is a boat. A gazetteer / relative / pin estimate
    # can land on a coastline; the projection must nudge it onto the sea.
    monkeypatch.setattr(
        "core.intel.landmask.is_on_land",
        lambda lat, lon: abs(lat - 35.5) < 0.01 and abs(lon - 14.0) < 0.01,
    )
    geom, _precision = public_geometry_and_precision(_event(coordinate_source="place_centroid"))
    assert geom["type"] == "Point"
    snapped_lon, snapped_lat = geom["coordinates"]
    assert (snapped_lat, snapped_lon) != (35.5, 14.0)
    assert not (abs(snapped_lat - 35.5) < 0.01 and abs(snapped_lon - 14.0) < 0.01)
