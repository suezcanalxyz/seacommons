from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from core.intel.satellite_observation import SatelliteObservation
from core.intel.satellite_resolver import (
    CopernicusSTACProvider,
    select_temporal_observations,
    viirs_daily_observations,
)


def _observation(identifier: str, acquired: str) -> SatelliteObservation:
    return SatelliteObservation(
        observation_id=identifier,
        incident_id="inc-1",
        provider="test",
        mission="test-mission",
        product_id=identifier,
        acquisition_time=acquired,
        discovered_at="2026-09-05T00:00:00+00:00",
        footprint=None,
        bbox=[14.0, 35.0, 14.2, 35.2],
        sensor_type="radar",
        temporal_relation="nearest",
        temporal_delta_s=0,
        asset_ref="https://example.test/asset",
        source_url="https://example.test/product",
        provenance={"source": "test"},
    )


def test_temporal_selector_returns_reverse_nearest_and_forward():
    event_time = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    observations = [
        _observation("old", "2026-09-03T18:00:00+00:00"),
        _observation("before", "2026-09-04T10:00:00+00:00"),
        _observation("after", "2026-09-04T13:00:00+00:00"),
    ]

    reverse = select_temporal_observations(observations, event_time, "reverse")
    nearest = select_temporal_observations(observations, event_time, "nearest")
    forward = select_temporal_observations(observations, event_time, "forward")

    assert [item.product_id for item in reverse] == ["before", "old"]
    assert [item.product_id for item in nearest] == ["after"]
    assert [item.product_id for item in forward] == ["after"]
    assert reverse[0].temporal_relation == "reverse"
    assert nearest[0].temporal_relation == "nearest"
    assert forward[0].temporal_relation == "forward"


def test_viirs_daily_context_builds_dated_gibs_layers():
    observations = viirs_daily_observations(
        incident_id="inc-1", lat=35.5, lon=14.1, day=date(2026, 9, 4)
    )
    assert {item.mission for item in observations} == {
        "VIIRS NOAA-20", "VIIRS NOAA-21", "VIIRS Suomi-NPP"
    }
    assert all(item.provider == "nasa_gibs" for item in observations)
    assert all("2026-09-04" in item.asset_ref for item in observations)
    assert all(item.provenance["temporal_precision"] == "day" for item in observations)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, url, *, json):
        self.calls.append((url, json))
        return _FakeResponse(self.payload)


def test_copernicus_stac_search_uses_bbox_datetime_and_normalizes_result():
    client = _FakeClient({
        "features": [{
            "id": "S1_TEST_PRODUCT",
            "bbox": [14.0, 35.0, 14.2, 35.2],
            "geometry": {"type": "Polygon", "coordinates": []},
            "properties": {"datetime": "2026-09-04T09:30:00Z", "platform": "sentinel-1c"},
            "assets": {"thumbnail": {"href": "https://example.test/s1-thumb.jpg"}},
            "links": [{"rel": "self", "href": "https://example.test/stac/S1_TEST_PRODUCT"}],
        }]
    })
    provider = CopernicusSTACProvider(client=client)
    observations = provider.search(
        incident_id="inc-1",
        bbox=[14.0, 35.0, 14.2, 35.2],
        start=datetime(2026, 9, 3, tzinfo=timezone.utc),
        end=datetime(2026, 9, 5, tzinfo=timezone.utc),
        collections=["sentinel-1-grd"],
    )
    assert len(client.calls) == 1
    url, body = client.calls[0]
    assert url.endswith("/search")
    assert body["bbox"] == [14.0, 35.0, 14.2, 35.2]
    assert body["collections"] == ["sentinel-1-grd"]
    assert "2026-09-03" in body["datetime"] and "2026-09-05" in body["datetime"]

    assert len(observations) == 1
    observation = observations[0]
    assert observation.provider == "copernicus_dataspace"
    assert observation.mission == "Sentinel-1"
    assert observation.product_id == "S1_TEST_PRODUCT"
    assert observation.asset_ref == "https://example.test/s1-thumb.jpg"
    assert observation.source_url == "https://example.test/stac/S1_TEST_PRODUCT"


def test_satellite_observation_persistence_is_idempotent():
    from core.db.models import SatelliteObservationDB
    from core.db.session import engine, session_scope
    from core.intel.satellite_observation import persist_observations

    SatelliteObservationDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(SatelliteObservationDB).delete()

    observation = _observation("persist-one", "2026-09-04T10:00:00+00:00")
    assert persist_observations([observation]) == 1
    assert persist_observations([observation]) == 0
    with session_scope() as db:
        assert db.query(SatelliteObservationDB).count() == 1


def test_resolve_for_incident_combines_free_sources_without_credentials():
    from core.intel.satellite_resolver import resolve_for_incident

    class FakeProvider:
        def __init__(self):
            self.calls = []

        def search(self, **kwargs):
            self.calls.append(kwargs)
            return [_observation("s1-before", "2026-09-04T10:00:00+00:00")]

    provider = FakeProvider()
    result = resolve_for_incident(
        incident_id="inc-1", lat=35.5, lon=14.1,
        event_time=datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc),
        direction="reverse", provider=provider, include_viirs=False,
    )
    assert [item.product_id for item in result] == ["s1-before"]
    assert result[0].temporal_relation == "reverse"
    assert provider.calls[0]["collections"] == [
        "sentinel-1-grd", "sentinel-2-l2a", "sentinel-3-olci-2-wfr-nrt"
    ]
    assert provider.calls[0]["bbox"] == [13.9, 35.3, 14.3, 35.7]


def test_forward_satellite_window_is_bounded_for_historical_play_case():
    from core.intel.satellite_resolver import resolve_for_incident

    class FakeProvider:
        def __init__(self):
            self.calls = []
        def search(self, **kwargs):
            self.calls.append(kwargs)
            return []

    provider = FakeProvider()
    event_time = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    resolve_for_incident(
        incident_id="historic", lat=35.5, lon=14.1,
        event_time=event_time, direction="forward", provider=provider,
        include_viirs=False, now=datetime(2026, 9, 5, tzinfo=timezone.utc),
    )
    assert provider.calls[0]["end"] <= event_time + timedelta(days=7)


def test_satellite_enrichment_keeps_recent_play_history_eligible():
    from core.intel.satellite_enrichment import is_satellite_enrichment_candidate
    from core.intel.store import IntelEvent
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    event = IntelEvent(
        id="historic-ap", timestamp_utc="2026-08-20T12:00:00+00:00",
        type="distress", severity="high", lat=35.5, lon=14.1,
        title="Historic distress", source="Alarm Phone",
        metadata={"is_distress": True, "publication_status": "published"},
    )
    assert is_satellite_enrichment_candidate(event, now=now, history_days=30) is True


def test_copernicus_stac_accepts_start_datetime_when_datetime_is_missing():
    client = _FakeClient({
        "features": [{
            "id": "S3_INTERVAL_PRODUCT",
            "collection": "sentinel-3-olci-2-wfr-nrt",
            "bbox": [14.0, 35.0, 14.2, 35.2],
            "geometry": {"type": "Polygon", "coordinates": []},
            "properties": {"start_datetime": "2026-09-04T09:30:00Z", "end_datetime": "2026-09-04T09:33:00Z", "platform": "sentinel-3a"},
            "assets": {"thumbnail": {"href": "https://example.test/s3-thumb.jpg"}},
            "links": [{"rel": "self", "href": "https://example.test/stac/S3_INTERVAL_PRODUCT"}],
        }]
    })
    observation = CopernicusSTACProvider(client=client).search(
        incident_id="inc-1", bbox=[14.0, 35.0, 14.2, 35.2],
        start=datetime(2026, 9, 3, tzinfo=timezone.utc), end=datetime(2026, 9, 5, tzinfo=timezone.utc),
        collections=["sentinel-3-olci-2-wfr-nrt"],
    )[0]
    assert observation.acquisition_time == "2026-09-04T09:30:00Z"
    assert observation.mission == "Sentinel-3"
