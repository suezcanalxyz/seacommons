"""Satellite search must never send malformed WGS84 targets or dateline boxes."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import pytest

from core.intel.satellite_enrichment import (
    _trajectory_targets,
    enrich_event,
    is_satellite_enrichment_candidate,
)
from core.intel.satellite_observation import SatelliteObservation
from core.intel.satellite_resolver import (
    _search_bboxes,
    resolve_for_incident,
    valid_wgs84_point,
    viirs_daily_observations,
)
from core.intel.store import IntelEvent


_NOW = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)


def _event(lat=35.5, lon=14.1):
    return IntelEvent(
        id="sat-coordinates-test", type="twitter", severity="high",
        lat=lat, lon=lon, source="Alarm Phone", title="Distress report",
        text="", timestamp_utc=_NOW.isoformat(),
        metadata={"is_distress": True, "maritime_domain": "sar"},
    )


@pytest.mark.parametrize("lat,lon", [
    (math.nan, 14.0), (35.0, math.inf), (91.0, 14.0),
    (-91.0, 14.0), (35.0, 181.0), (35.0, -181.0),
    (True, 14.0), (35.0, False), ("35.0", 14.0),
    (35.0, "14.0"), (10**1000, 14.0),
])
def test_invalid_origin_never_becomes_satellite_candidate(lat, lon, monkeypatch):
    assert not valid_wgs84_point(lat, lon)
    event = _event(lat, lon)
    assert not is_satellite_enrichment_candidate(event, now=_NOW)
    monkeypatch.setattr(
        "core.intel.satellite_enrichment.resolve_for_incident",
        lambda **_: pytest.fail("invalid origin queried remote satellite provider"),
    )
    assert enrich_event(event, now=_NOW) == {"persisted": 0, "errors": 0}


def test_valid_coordinate_edges():
    assert valid_wgs84_point(90, 180)
    assert valid_wgs84_point(-90, -180)
    assert valid_wgs84_point(0, 0)


def _trajectory():
    return {
        "geometry": {"type": "LineString", "coordinates": [
            [14.0, 35.0], [14.1, 35.1], [14.2, 35.2], [14.3, 35.3],
        ]},
        "properties": {"timestamps_utc": [
            (_NOW + timedelta(hours=h)).isoformat() for h in range(4)
        ]},
    }


@pytest.mark.parametrize("bad_point", [
    [181, 35.1], [14.1, -95], [math.nan, 35.1],
    [14.1, math.inf], ["14.1", 35.1], [14.1, True], [14.1],
])
def test_bad_intermediate_trajectory_point_blocks_all_targets(bad_point):
    trajectory = _trajectory()
    trajectory["geometry"]["coordinates"][1] = bad_point
    assert _trajectory_targets(trajectory, drift_id="drift", limit=1) == []


def test_reversed_or_duplicate_intermediate_timestamps_block_targets():
    for bad_hour in (0, -1):
        trajectory = _trajectory()
        trajectory["properties"]["timestamps_utc"][2] = (
            _NOW + timedelta(hours=bad_hour)
        ).isoformat()
        assert _trajectory_targets(trajectory, drift_id="drift", limit=1) == []


def test_valid_trajectory_still_returns_bounded_targets():
    targets = _trajectory_targets(_trajectory(), drift_id="drift", limit=2)
    assert len(targets) == 2
    assert targets[-1]["lat"] == 35.3
    assert targets[-1]["lon"] == 14.3


def test_antimeridian_and_pole_bboxes_are_valid():
    for lat, lon in [(35, 179.95), (35, -179.95), (89.95, 14), (-89.95, 14)]:
        boxes = _search_bboxes(lat, lon, 0.2)
        assert len(boxes) == (2 if abs(lon) > 179 else 1)
        for west, south, east, north in boxes:
            assert -180 <= west <= east <= 180
            assert -90 <= south <= north <= 90


@pytest.mark.parametrize("radius", [0, -1, math.nan, math.inf, 6, True])
def test_invalid_radius_rejected_before_remote_request(radius):
    with pytest.raises(ValueError):
        _search_bboxes(35, 14, radius)


def test_antimeridian_stac_queries_split_and_dedupe():
    class FakeProvider:
        def __init__(self):
            self.boxes = []

        def search(self, **kwargs):
            self.boxes.append(kwargs["bbox"])
            identifier = "scene-shared" if len(self.boxes) == 1 else "scene-new"
            return [
                SatelliteObservation(
                    observation_id="shared", incident_id="incident",
                    provider="copernicus_dataspace", mission="Sentinel-1",
                    product_id="shared", acquisition_time=(_NOW - timedelta(hours=1)).isoformat(),
                    discovered_at=_NOW.isoformat(), footprint=None, bbox=None,
                    sensor_type="sar", temporal_relation="reverse", temporal_delta_s=0,
                    asset_ref="", source_url="", provenance={},
                ),
                SatelliteObservation(
                    observation_id=identifier, incident_id="incident",
                    provider="copernicus_dataspace", mission="Sentinel-1",
                    product_id=identifier, acquisition_time=(_NOW - timedelta(hours=1)).isoformat(),
                    discovered_at=_NOW.isoformat(), footprint=None, bbox=None,
                    sensor_type="sar", temporal_relation="reverse", temporal_delta_s=0,
                    asset_ref="", source_url="", provenance={},
                ),
            ]

    provider = FakeProvider()
    result = resolve_for_incident(
        incident_id="incident", lat=35, lon=179.95,
        event_time=_NOW, direction="reverse", provider=provider,
        include_viirs=False, radius_deg=0.2,
    )
    assert len(provider.boxes) == 2
    assert len(result) == 3
    assert {item.observation_id for item in result} == {
        "shared", "scene-shared", "scene-new",
    }


def test_nasa_viirs_context_near_dateline_keeps_valid_bbox():
    observations = viirs_daily_observations(
        incident_id="incident", lat=35, lon=179.99, day=date(2026, 11, 1),
    )
    assert len(observations) == 3
    assert all(-180 <= item.bbox[0] <= item.bbox[2] <= 180 for item in observations)
    assert all(len(item.provenance["search_bboxes"]) == 2 for item in observations)
