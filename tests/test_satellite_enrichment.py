from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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
        type="correlated_alert", source="Maritime Security",
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


def test_trajectory_sampling_keeps_past_positions_when_forecast_dominates():
    from core.intel.satellite_enrichment import _trajectory_targets

    trajectory = {
        "geometry": {
            "type": "LineString",
            "coordinates": [[14.0 + index / 100, 35.0 + index / 100]
                            for index in range(10)],
        },
        "properties": {
            "timestamps_utc": [
                (_NOW + timedelta(hours=index)).isoformat()
                for index in range(10)
            ],
        },
    }
    cutoff = _NOW + timedelta(hours=2, minutes=30)
    # Previously the sampler chose points 1, 5 and 9; the later
    # future-point gate discarded 5 and 9, losing the valid point 2.
    targets = _trajectory_targets(
        trajectory, drift_id="mixed-forecast", limit=3, not_after=cutoff,
    )
    assert [target["trajectory_index"] for target in targets] == [1, 2]
    assert all(target["at"] <= cutoff for target in targets)
    assert _trajectory_targets(
        trajectory, drift_id="mixed-forecast", limit=3, not_after=_NOW,
    ) == []


def test_enrich_event_supplies_clock_to_trajectory_sampling(monkeypatch):
    from core.intel import satellite_enrichment

    cutoffs = []
    monkeypatch.setattr(
        satellite_enrichment,
        "_case_satellite_targets",
        lambda _event, *, now: cutoffs.append(now) or [],
    )
    assert satellite_enrichment.enrich_event(
        _event(), now=_NOW, include_viirs=False,
    ) == {"persisted": 0, "errors": 0}
    assert cutoffs == [_NOW]


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
        lambda _event, **_kwargs: [
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

    report = satellite_enrichment.enrich_event(_event(), now=_NOW + timedelta(hours=3), include_viirs=False)
    assert [row[3] for row in calls] == ["reverse", "nearest", "forward", "nearest"]
    assert calls[-1][:2] == (35.6, 14.2)
    assert calls[-1][2] == _NOW + timedelta(hours=2)
    assert persisted[-1].provenance["case_targets"][0]["role"] == "drift_trajectory"
    assert persisted[-1].provenance["case_targets"][0]["drift_id"] == "drift-1"
    assert report == {"persisted": 4, "errors": 0}


def test_satellite_skips_future_drift_prediction_but_keeps_past_targets(monkeypatch):
    from core.intel import satellite_enrichment

    calls = []
    now = _NOW + timedelta(minutes=30)
    monkeypatch.setattr(
        satellite_enrichment,
        "_case_satellite_targets",
        lambda _event, **_kwargs: [
            {"role": "reported_origin", "lat": 35.5, "lon": 14.1, "at": _NOW},
            {"role": "drift_trajectory", "lat": 35.6, "lon": 14.2,
             "at": _NOW + timedelta(hours=1), "drift_id": "future-drift"},
            {"role": "drift_trajectory", "lat": 35.7, "lon": 14.3,
             "at": _NOW + timedelta(minutes=10), "drift_id": "past-drift"},
        ],
    )

    def fake_resolve_for_incident(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(satellite_enrichment, "resolve_for_incident", fake_resolve_for_incident)
    monkeypatch.setattr(satellite_enrichment, "persist_observations", lambda rows: 0)

    result = satellite_enrichment.enrich_event(_event(), now=now, include_viirs=False)
    assert result == {"persisted": 0, "errors": 0}
    assert [row["direction"] for row in calls] == ["reverse", "nearest", "forward", "nearest"]
    assert calls[-1]["event_time"] == _NOW + timedelta(minutes=10)
    assert all(row["event_time"] <= now for row in calls)
    assert not any(row["lat"] == 35.6 for row in calls)


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


def test_satellite_rejects_missing_or_unparseable_report_time(monkeypatch):
    from core.intel import satellite_enrichment

    monkeypatch.setattr(
        satellite_enrichment, "resolve_for_incident",
        lambda **_: pytest.fail("undated report queried a satellite provider"),
    )
    for timestamp in (None, "", "not-a-timestamp"):
        event = _event(timestamp_utc=timestamp)
        if not timestamp:
            # IntelEvent retains an ingest timestamp for legacy ordering,
            # but records that it is not an observed source timestamp.
            assert event.timestamp_utc
            assert event.metadata["_source_timestamp_inferred"] is True
        assert not satellite_enrichment.is_satellite_enrichment_candidate(event, now=_NOW)
        assert satellite_enrichment._case_satellite_targets(event) == []
        assert satellite_enrichment.enrich_event(event, now=_NOW) == {
            "persisted": 0, "errors": 0,
        }


def test_satellite_rejects_future_report_without_provider_call(monkeypatch):
    from core.intel import satellite_enrichment

    monkeypatch.setattr(
        satellite_enrichment, "resolve_for_incident",
        lambda **_: pytest.fail("future-dated report queried a satellite provider"),
    )
    event = _event(timestamp_utc=(_NOW + timedelta(minutes=6)).isoformat())
    assert not satellite_enrichment.is_satellite_enrichment_candidate(event, now=_NOW)
    assert satellite_enrichment.enrich_event(event, now=_NOW) == {
        "persisted": 0, "errors": 0,
    }
    # Allow small clock skew without inventing an observation time.
    skewed = _event(timestamp_utc=(_NOW + timedelta(minutes=4)).isoformat())
    assert satellite_enrichment.is_satellite_enrichment_candidate(skewed, now=_NOW)


def test_false_string_flags_do_not_trigger_satellite_enrichment():
    from core.intel.satellite_enrichment import is_satellite_enrichment_candidate

    false_flags = _event(metadata={
        "is_distress": "false", "drift_eligible": "false",
    })
    assert not is_satellite_enrichment_candidate(false_flags, now=_NOW)
    positive = _event(metadata={"is_distress": "true"})
    assert is_satellite_enrichment_candidate(positive, now=_NOW)
    published = _event(source="Maritime Security", metadata={
        "publication_status": "published", "maritime_domain": "grey_zone",
    })
    assert is_satellite_enrichment_candidate(published, now=_NOW)



def test_satellite_accepts_explicit_source_time_without_inference_marker():
    from core.intel import satellite_enrichment

    event = _event(timestamp_utc=_NOW.isoformat())
    assert "_source_timestamp_inferred" not in event.metadata
    assert satellite_enrichment._credible_source_time(event) == _NOW
    assert satellite_enrichment.is_satellite_enrichment_candidate(event, now=_NOW)


@pytest.mark.parametrize("source", [
    "Alarm Phone", "alarm_phone", "alarmphone", "@alarm_phone",
    "AlarmPhone", "@AlarmPhone", "@alarmphone",
])
def test_satellite_recovers_durable_alarm_phone_aliases_for_play(monkeypatch, source):
    """An AIS-evicted SAR report remains discoverable across source spellings."""
    from core.intel import satellite_enrichment
    from core.intel.store import intel_store

    historical = _event(
        source=source,
        timestamp_utc=(_NOW - timedelta(days=15)).isoformat(),
    )
    reads = []
    enriched = []
    monkeypatch.setattr(intel_store, "events", lambda **_kwargs: [])

    def persisted_events(**kwargs):
        reads.append(kwargs)
        return [historical] if source in kwargs["source_in"] else []

    monkeypatch.setattr(intel_store, "persisted_events", persisted_events)
    monkeypatch.setattr(intel_store, "update_metadata", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        satellite_enrichment, "enrich_event",
        lambda event, **_kwargs: enriched.append(event.id) or {
            "persisted": 1, "errors": 0,
        },
    )
    report = satellite_enrichment.enrich_recent_events(limit=1, now=_NOW)
    assert reads[0]["max_age_days"] == satellite_enrichment.PLAY_HUMANITARIAN_HISTORY_DAYS
    assert enriched == [historical.id]
    assert report == {"scanned": 1, "enriched": 1, "persisted": 1, "errors": 0}


def test_satellite_durable_alias_does_not_promote_false_distress(monkeypatch):
    from core.intel import satellite_enrichment
    from core.intel.store import intel_store

    contextual = _event(
        source="@alarmphone",
        metadata={"is_distress": "false", "drift_eligible": "false"},
    )
    monkeypatch.setattr(intel_store, "events", lambda **_kwargs: [])
    monkeypatch.setattr(
        intel_store, "persisted_events",
        lambda **_kwargs: [contextual],
    )
    monkeypatch.setattr(
        satellite_enrichment, "enrich_event",
        lambda *_args, **_kwargs: pytest.fail("contextual report queried a provider"),
    )
    assert satellite_enrichment.enrich_recent_events(limit=1, now=_NOW) == {
        "scanned": 1, "enriched": 0, "persisted": 0, "errors": 0,
    }


@pytest.mark.parametrize("source,metadata", [
    ("Alarm Phone", {"publication_status": "published", "maritime_domain": "sar", "is_distress": "false"}),
    ("@alarmphone", {"publication_status": "published", "is_distress": False}),
    ("AlarmPhone", {"publication_status": "published"}),
    ("Sea Watch", {"publication_status": "published", "maritime_domain": "sar", "is_distress": False}),
])
def test_published_humanitarian_context_does_not_trigger_satellite_queries(monkeypatch, source, metadata):
    from core.intel import satellite_enrichment

    contextual = _event(source=source, metadata=metadata)
    monkeypatch.setattr(
        satellite_enrichment, "resolve_for_incident",
        lambda **_kwargs: pytest.fail("non-distress humanitarian context queried a satellite provider"),
    )
    assert not satellite_enrichment.is_satellite_enrichment_candidate(contextual, now=_NOW)
    assert satellite_enrichment.enrich_event(contextual, now=_NOW) == {
        "persisted": 0, "errors": 0,
    }


def test_satellite_explicit_negative_distress_overrides_stale_drift_eligibility():
    from core.intel.satellite_enrichment import is_satellite_enrichment_candidate

    stale = _event(metadata={
        "maritime_domain": "sar", "publication_status": "published",
        "is_distress": "false", "drift_eligible": "true",
    })
    assert not is_satellite_enrichment_candidate(stale, now=_NOW)


def test_satellite_keeps_published_maritime_and_explicit_sar_distress():
    from core.intel.satellite_enrichment import is_satellite_enrichment_candidate

    maritime = _event(
        source="Maritime Security", metadata={
            "maritime_domain": "grey_zone", "publication_status": "published",
        },
    )
    sar = _event(
        source="@alarmphone", metadata={
            "maritime_domain": "sar", "is_distress": "true",
            "publication_status": "published",
        },
    )
    assert is_satellite_enrichment_candidate(maritime, now=_NOW)
    assert is_satellite_enrichment_candidate(sar, now=_NOW)


@pytest.mark.parametrize("metadata", [
    {"coordinate_source": "place_centroid", "location_uncertainty_m": 500},
    {"coordinate_source": "region_area"},
    {"coordinate_review_status": "needs_review", "location_uncertainty_m": 100},
    {"coordinate_review_status": "disputed"},
    {"location_status": "withheld_from_maritime_map"},
    {"location_status": "region_only"},
    {"location_uncertainty_m": 44290},
    {"location_uncertainty_m": "NaN"},
    {"location_uncertainty_m": "Infinity"},
    {"location_uncertainty_m": -1},
    {"location_uncertainty_m": "unknown"},
    {"location_uncertainty_m": True},
])
def test_satellite_rejects_unreliable_geographic_targets_without_provider_calls(monkeypatch, metadata):
    from core.intel import satellite_enrichment

    event = _event(metadata={
        "maritime_domain": "sar", "is_distress": True, **metadata,
    })
    monkeypatch.setattr(
        satellite_enrichment, "resolve_for_incident",
        lambda **_kwargs: pytest.fail("unreliable coordinates queried a satellite provider"),
    )
    assert not satellite_enrichment.is_satellite_enrichment_candidate(event, now=_NOW)
    assert satellite_enrichment.enrich_event(event, now=_NOW) == {
        "persisted": 0, "errors": 0,
    }


def test_satellite_accepts_bounded_uncertainty_and_trusted_point_with_stale_region_label():
    from core.intel.satellite_enrichment import is_satellite_enrichment_candidate

    reviewed = _event(metadata={
        "maritime_domain": "sar", "is_distress": True,
        "coordinate_source": "media_ocr_text",
        "coordinate_review_status": "machine_ocr_unverified",
        "location_uncertainty_m": 3200,
        "location_status": "unpositioned",
    })
    assert is_satellite_enrichment_candidate(reviewed, now=_NOW)
    published_maritime = _event(source="Maritime Security", metadata={
        "publication_status": "published", "maritime_domain": "grey_zone",
        "coordinate_source": "ais_position", "location_uncertainty_m": 300,
    })
    assert is_satellite_enrichment_candidate(published_maritime, now=_NOW)


def test_satellite_rejects_unreliable_published_maritime_coordinate():
    from core.intel.satellite_enrichment import is_satellite_enrichment_candidate

    maritime = _event(source="Maritime Security", metadata={
        "publication_status": "published", "maritime_domain": "grey_zone",
        "coordinate_source": "place_centroid",
    })
    assert not is_satellite_enrichment_candidate(maritime, now=_NOW)
