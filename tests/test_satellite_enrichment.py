from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.intel.store import IntelEvent

_NOW = datetime(2026, 9, 5, 0, 0, tzinfo=timezone.utc)


def _event(**overrides):
    values = {
        "id": "sat-event-1", "type": "twitter", "severity": "high",
        "lat": 35.5, "lon": 14.1, "source": "Alarm Phone",
        "title": "Distress report", "text": "", "timestamp_utc": _NOW.isoformat(),
        "metadata": {"is_distress": True, "maritime_domain": "sar"},
    }
    values.update(overrides)
    return IntelEvent(**values)


def test_satellite_enrichment_eligibility_is_signal_gated():
    from core.intel.satellite_enrichment import is_satellite_enrichment_candidate

    assert is_satellite_enrichment_candidate(_event(), now=_NOW) is True
    assert is_satellite_enrichment_candidate(_event(lat=None), now=_NOW) is False
    raw_ais = _event(type="ais_anomaly", metadata={"maritime_domain": "grey_zone"})
    assert is_satellite_enrichment_candidate(raw_ais, now=_NOW) is False


def test_published_maritime_event_is_candidate_but_old_event_is_not():
    from core.intel.satellite_enrichment import is_satellite_enrichment_candidate

    maritime = _event(
        type="correlated_alert",
        metadata={"publication_status": "published", "maritime_domain": "grey_zone"},
    )
    assert is_satellite_enrichment_candidate(maritime, now=_NOW) is True

    old = _event(timestamp_utc=(_NOW - timedelta(days=8)).isoformat())
    assert is_satellite_enrichment_candidate(old, now=_NOW) is False


def test_trajectory_targets_sample_case_drift_over_time():
    from core.intel.satellite_enrichment import _trajectory_targets

    trajectory = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [14.0, 35.0],
                [14.1, 35.1],
                [14.2, 35.2],
                [14.3, 35.3],
                [14.4, 35.4],
            ],
        },
        "properties": {
            "timestamps_utc": [
                "2026-09-05T00:00:00Z",
                "2026-09-05T01:00:00Z",
                "2026-09-05T02:00:00Z",
                "2026-09-05T03:00:00Z",
                "2026-09-05T04:00:00Z",
            ]
        },
    }
    targets = _trajectory_targets(trajectory, drift_id="drift-1", limit=3)
    assert len(targets) == 3
    assert all(row["role"] == "drift_trajectory" for row in targets)
    assert all(row["drift_id"] == "drift-1" for row in targets)
    assert targets[-1]["lat"] == 35.4
    assert targets[-1]["lon"] == 14.4
    assert targets[-1]["at"].hour == 4


def test_enrich_event_queries_reverse_nearest_forward_and_persists(monkeypatch):
    from core.intel import satellite_enrichment
    from core.intel.satellite_observation import SatelliteObservation

    calls = []
    persisted = []

    def fake_resolve_for_incident(**kwargs):
        calls.append(kwargs["direction"])
        return [SatelliteObservation(
            observation_id=f"sat-{kwargs['direction']}", incident_id=kwargs["incident_id"],
            provider="test", mission="Sentinel-1", product_id=kwargs["direction"],
            acquisition_time=_NOW.isoformat(), discovered_at=_NOW.isoformat(),
            footprint=None, bbox=None, sensor_type="sar",
            temporal_relation=kwargs["direction"], temporal_delta_s=0,
            asset_ref="", source_url="", provenance={},
        )]

    monkeypatch.setattr(satellite_enrichment, "resolve_for_incident", fake_resolve_for_incident)
    monkeypatch.setattr(satellite_enrichment, "persist_observations", lambda rows: persisted.extend(rows) or len(rows))

    report = satellite_enrichment.enrich_event(_event(), now=_NOW, include_viirs=False)
    assert calls == ["reverse", "nearest", "forward"]
    assert len(persisted) == 3
    assert report["persisted"] == 3
    assert report["errors"] == 0


def test_enrich_event_adds_nearest_searches_for_drift_targets(monkeypatch):
    from core.intel import satellite_enrichment
    from core.intel.satellite_observation import SatelliteObservation

    calls = []
    persisted = []

    monkeypatch.setattr(
        satellite_enrichment,
        "_case_satellite_targets",
        lambda _event: [
            {"role": "reported_origin", "lat": 35.5, "lon": 14.1, "at": _NOW},
            {
                "role": "drift_trajectory", "lat": 35.6, "lon": 14.2,
                "at": _NOW + timedelta(hours=2), "drift_id": "drift-1",
                "trajectory_index": 2,
            },
        ],
    )

    def fake_resolve_for_incident(**kwargs):
        calls.append((kwargs["lat"], kwargs["lon"], kwargs["event_time"], kwargs["direction"]))
        return [SatelliteObservation(
            observation_id=f"sat-{len(calls)}", incident_id=kwargs["incident_id"],
            provider="test", mission="Sentinel-1", product_id=str(len(calls)),
            acquisition_time=kwargs["event_time"].isoformat(),
            discovered_at=_NOW.isoformat(), footprint=None, bbox=None,
            sensor_type="sar", temporal_relation=kwargs["direction"],
            temporal_delta_s=0, asset_ref="", source_url="", provenance={},
        )]

    monkeypatch.setattr(satellite_enrichment, "resolve_for_incident", fake_resolve_for_incident)
    monkeypatch.setattr(
        satellite_enrichment,
        "persist_observations",
        lambda rows: persisted.extend(rows) or len(rows),
    )

    report = satellite_enrichment.enrich_event(_event(), now=_NOW, include_viirs=False)
    assert [row[3] for row in calls] == ["reverse", "nearest", "forward", "nearest"]
    assert calls[-1][:2] == (35.6, 14.2)
    assert calls[-1][2] == _NOW + timedelta(hours=2)
    assert persisted[-1].provenance["case_targets"][0]["role"] == "drift_trajectory"
    assert persisted[-1].provenance["case_targets"][0]["drift_id"] == "drift-1"
    assert report == {"persisted": 4, "errors": 0}


def test_enrich_event_degrades_safely_when_provider_fails(monkeypatch):
    from core.intel import satellite_enrichment

    def fail(**_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(satellite_enrichment, "resolve_for_incident", fail)
    report = satellite_enrichment.enrich_event(_event(), now=_NOW, include_viirs=False)
    assert report == {"persisted": 0, "errors": 3}


def test_scheduler_satellite_job_calls_bounded_enrichment(monkeypatch):
    from core import scheduler

    calls = []
    monkeypatch.setattr(
        "core.intel.satellite_enrichment.enrich_recent_events",
        lambda **kwargs: calls.append(kwargs) or {"scanned": 4, "enriched": 2, "persisted": 5, "errors": 0},
    )
    scheduler._job_satellite_enrichment()
    assert calls == [{"limit": 6}]


def test_region_area_satellite_target_uses_uncertainty_not_precise_origin():
    from core.intel.satellite_enrichment import _case_satellite_targets

    event = _event(metadata={
        "is_distress": True,
        "maritime_domain": "sar",
        "coordinate_source": "region_area",
        "location_uncertainty_m": 180000,
    }, lat=37.5, lon=1.5)
    targets = _case_satellite_targets(event)
    assert targets[0]["role"] == "reported_search_area"
    assert 1.5 < targets[0]["radius_deg"] < 1.7


def test_enrich_region_area_passes_broad_radius_and_records_it(monkeypatch):
    from core.intel import satellite_enrichment
    from core.intel.satellite_observation import SatelliteObservation

    calls = []
    persisted = []
    event = _event(metadata={
        "is_distress": True,
        "coordinate_source": "region_area",
        "location_uncertainty_m": 180000,
    }, lat=37.5, lon=1.5)

    def fake_resolve_for_incident(**kwargs):
        calls.append(kwargs)
        return [SatelliteObservation(
            observation_id=f"sat-region-{len(calls)}", incident_id=kwargs["incident_id"],
            provider="test", mission="Sentinel-1", product_id=str(len(calls)),
            acquisition_time=kwargs["event_time"].isoformat(), discovered_at=_NOW.isoformat(),
            footprint=None, bbox=None, sensor_type="sar",
            temporal_relation=kwargs["direction"], temporal_delta_s=0,
            asset_ref="", source_url="", provenance={},
        )]

    monkeypatch.setattr(satellite_enrichment, "resolve_for_incident", fake_resolve_for_incident)
    monkeypatch.setattr(satellite_enrichment, "persist_observations", lambda rows: persisted.extend(rows) or len(rows))
    report = satellite_enrichment.enrich_event(event, now=_NOW, include_viirs=False)
    assert report["errors"] == 0
    assert all(call["radius_deg"] > 1.5 for call in calls[:3])
    target = persisted[0].provenance["case_targets"][0]
    assert target["role"] == "reported_search_area"
    assert target["search_radius_deg"] > 1.5


def test_trajectory_targets_reject_invalid_geographic_coordinates():
    from core.intel.satellite_enrichment import _trajectory_targets

    trajectory = {
        'geometry': {'type': 'LineString', 'coordinates': [
            [14, 35], [float('nan'), 35], [200, 35], ['not-a-longitude', 35], [14.4, 35.4],
        ]},
        'properties': {'timestamps_utc': [
            '2026-09-05T00:00:00Z', '2026-09-05T01:00:00Z',
            '2026-09-05T02:00:00Z', '2026-09-05T03:00:00Z',
            '2026-09-05T04:00:00Z',
        ]},
    }
    targets = _trajectory_targets(trajectory, drift_id='invalid-coords', limit=4)
    assert len(targets) == 1
    assert targets[0]['lon'] == 14.4
    assert targets[0]['lat'] == 35.4


def test_trajectory_sampling_skips_invalid_before_spending_budget():
    from core.intel.satellite_enrichment import _trajectory_targets
    coords = [[14.0, 35.0], [14.1, 35.1], [200.0, 35.2],
              [14.3, 35.3], [float('nan'), 35.4], [14.5, 35.5]]
    trajectory = {
        'geometry': {'type': 'LineString', 'coordinates': coords},
        'properties': {'timestamps_utc': [f'2026-09-05T0{i}:00:00Z' for i in range(6)]},
    }
    targets = _trajectory_targets(trajectory, drift_id='mixed', limit=3)
    assert len(targets) == 3
    assert [target['trajectory_index'] for target in targets] == [1, 3, 5]
    assert all(-180 <= target['lon'] <= 180 for target in targets)
