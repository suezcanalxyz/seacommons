from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from core.intel.hypothesis_engine import _canonical_verification


def test_multi_source_invariant_requires_two_independent_lineages():
    assert _canonical_verification(["modality:ais"], 8) == "single_source_multi_indicator"
    assert _canonical_verification(["modality:ais", "source:satellite:gfw"], 2) == "multi_source_corroborated"
    assert _canonical_verification([], 1) == "single_source_observed"


def test_satellite_coverage_queue_is_context_only():
    from core.db.models import MaritimeEpisodeDB, SatelliteObservationDB
    from core.db.session import session_scope
    from core.intel.correlation_stabilization import satellite_coverage_queue

    now = datetime.now(timezone.utc)
    with session_scope() as db:
        db.add(MaritimeEpisodeDB(
            episode_id="episode:test:sat",
            episode_family="spoofing_episode",
            subject_ids=["subj:mmsi:123456789"],
            start_at=(now - timedelta(hours=1)).replace(tzinfo=None),
            end_at=now.replace(tzinfo=None),
            geometry={"type": "Point", "coordinates": [14.0, 35.0]},
            observation_ids=["event:test"],
            feature_ids=[],
            independence_groups=["ais_sensor_lineage"],
            verification_status="single_source_observed",
            behaviour_context={},
            alternative_explanations=[],
            evidence_fingerprint="x" * 64,
            method_version="test-v1",
            status="active",
        ))
        db.add(SatelliteObservationDB(
            observation_id="sat:test:coverage",
            incident_id="event:other",
            provider="copernicus",
            mission="sentinel1",
            product_id="product:test",
            acquisition_time=now.isoformat(),
            discovered_at=now.replace(tzinfo=None),
            footprint={"type": "Polygon", "coordinates": []},
            bbox=[13.0, 34.0, 15.0, 36.0],
            sensor_type="sar",
            temporal_relation="nearest",
            temporal_delta_s=0.0,
            evidence_status="contextual",
            association_status=None,
        ))

    payload = satellite_coverage_queue(hours=24, temporal_hours=12, limit=10)
    assert payload["total_candidates"] == 1
    assert payload["items"][0]["episode_id"] == "episode:test:sat"
    assert payload["items"][0]["evidence_role"] == "context_only_pending_review"
    assert payload["items"][0]["scenes"][0]["observation_id"] == "sat:test:coverage"


def test_humanitarian_ais_proximity_stays_context_without_identity_link():
    from core.db.models import IntelEventDB, VesselTrackDB
    from core.db.session import session_scope
    from core.intel.correlation_stabilization import humanitarian_ais_correlation

    now = datetime.now(timezone.utc)
    with session_scope() as db:
        db.add(IntelEventDB(
            id="human:test",
            timestamp_utc=now.isoformat(),
            type="twitter",
            severity="high",
            lat=35.0,
            lon=14.0,
            title="People in distress",
            source="alarm_phone",
            linked_mmsi="",
            meta={"maritime_domain": "sar"},
            maritime_domain="sar",
            received_at=now.replace(tzinfo=None),
            created_at=now.replace(tzinfo=None),
        ))
        db.add(VesselTrackDB(
            mmsi="123456789",
            ts=now.replace(tzinfo=None),
            received_at=now.replace(tzinfo=None),
            lat=35.02,
            lon=14.02,
            sog=10.0,
            cog=225.0,
            heading=225.0,
            nav_status=0,
            source="test",
        ))

    payload = humanitarian_ais_correlation(hours=24, radius_nm=35, window_hours=2)
    assert payload["count"] == 1
    candidates = payload["items"][0]["candidates"]
    assert candidates
    assert candidates[0]["association_status"] == "contextual_response_candidate"
    assert candidates[0]["evidence_role"] == "context_only"


def test_humanitarian_explicit_mmsi_can_be_strong_identity_link():
    from core.db.models import IntelEventDB, VesselTrackDB
    from core.db.session import session_scope
    from core.intel.correlation_stabilization import humanitarian_ais_correlation

    now = datetime.now(timezone.utc)
    with session_scope() as db:
        db.add(IntelEventDB(
            id="human:linked",
            timestamp_utc=now.isoformat(),
            type="news",
            severity="high",
            lat=35.0,
            lon=14.0,
            title="Named vessel response",
            source="SOSMedIntl",
            linked_mmsi="123456789",
            meta={"maritime_domain": "sar"},
            maritime_domain="sar",
            received_at=now.replace(tzinfo=None),
            created_at=now.replace(tzinfo=None),
        ))
        db.add(VesselTrackDB(
            mmsi="123456789",
            ts=now.replace(tzinfo=None),
            received_at=now.replace(tzinfo=None),
            lat=35.01,
            lon=14.01,
            sog=8.0,
            cog=220.0,
            heading=220.0,
            nav_status=0,
            source="test",
        ))

    payload = humanitarian_ais_correlation(hours=24)
    candidate = payload["items"][0]["candidates"][0]
    assert candidate["association_status"] == "strong_identity_link"
    assert candidate["evidence_role"] == "corroboration"


def test_vessel_search_filters_by_ship_type(monkeypatch):
    from core.api.main import app
    from core.vessels.registry import registry

    monkeypatch.setattr(registry, "get_geojson", lambda: {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [14.0, 35.0]},
                "properties": {
                    "mmsi": "111111111", "ship_name": "TANKER ONE",
                    "imo": "9000001", "ship_type": 80, "destination": "MALTA",
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [15.0, 36.0]},
                "properties": {
                    "mmsi": "222222222", "ship_name": "CARGO ONE",
                    "imo": "9000002", "ship_type": 70, "destination": "GENOA",
                },
            },
        ],
    })
    response = TestClient(app).get("/api/v1/vessels/search?ship_type=tanker")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_matches"] == 1
    assert payload["vessels"][0]["mmsi"] == "111111111"
    assert payload["vessels"][0]["ship_type_label"] == "TANKER"


def test_reconciler_closes_strong_satellite_onto_canonical_episode():
    from core.db.models import MaritimeEpisodeDB, SatelliteObservationDB
    from core.db.session import session_scope
    from core.intel.hypothesis_engine import reconcile_cross_modal_episodes
    from core.intel.store import IntelEvent, intel_store

    now = datetime.now(timezone.utc)
    episode_id = "episode:test:reconcile-satellite"
    event_id = "aisgap:123456789:reconcile"
    intel_store.add(IntelEvent(
        id=event_id,
        type="ais_anomaly",
        severity="high",
        lat=35.0,
        lon=14.0,
        title="test strong satellite gap",
        source="mda",
        linked_mmsi="123456789",
        timestamp_utc=now.isoformat(),
        metadata={
            "anomaly_type": "gap",
            "gap_reason": {"hypothesis": "vessel_gap", "confidence": 0.9},
            "publication_status": "published",
            "analysis_state": "evidence_candidate",
        },
    ), dedup_key=event_id)
    with session_scope() as db:
        db.add(MaritimeEpisodeDB(
            episode_id=episode_id,
            episode_family="gap_episode",
            subject_ids=["subj:mmsi:123456789"],
            start_at=now.replace(tzinfo=None),
            end_at=now.replace(tzinfo=None),
            geometry={"type": "Point", "coordinates": [14.0, 35.0]},
            observation_ids=[event_id],
            feature_ids=[],
            independence_groups=["ais_sensor_lineage"],
            verification_status="single_source_observed",
            behaviour_context={"analysis": {
                "analysis_state": "evidence_candidate",
                "publication_state": "published",
                "resolution_state": "open",
            }},
            alternative_explanations=[],
            evidence_fingerprint="reconcile-test",
            method_version="test",
            status="active",
        ))
        db.add(SatelliteObservationDB(
            observation_id="sat:test:strong-reconcile",
            incident_id=event_id,
            provider="gfw",
            mission="sentinel1",
            product_id="gfw:test",
            acquisition_time=now.isoformat(),
            discovered_at=now.replace(tzinfo=None),
            footprint={"type": "Point", "coordinates": [14.0, 35.0]},
            bbox=[13.9, 34.9, 14.1, 35.1],
            sensor_type="sar",
            temporal_relation="nearest",
            temporal_delta_s=0.0,
            evidence_status="associated",
            association_status="strong",
            episode_id=episode_id,
        ))

    result = reconcile_cross_modal_episodes(hours=24, limit=20)
    assert result["evaluated"] >= 1
    with session_scope() as db:
        row = db.get(MaritimeEpisodeDB, episode_id)
        assert row is not None
        assert row.verification_status == "multi_source_corroborated"
        assert len(set(row.independence_groups or ())) >= 2


def test_operator_stabilization_exposes_quality_slos(monkeypatch):
    from core.api.main import app
    from core.api.routes import operator_ingestion
    from core.config import config

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    operator_ingestion._fast_cache.clear()
    response = TestClient(app).get(
        "/api/v1/operator/ingestion/stabilization?hours=24",
        headers={"x-seacommons-operator-gateway": "operator-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert set(payload["rates"]) == {
        "derived_to_episode",
        "episode_to_multi_lineage",
        "multi_lineage_to_review_ready",
    }
    assert payload["invariants"]["ok"] is True
    assert "satellite_coverage_candidates" in payload["counts"]
    assert "ready_for_scale" in payload["radio"]


def test_ais_ship_type_labels_cover_operational_families():
    from core.vessels.aisstream import _ship_type_label

    assert _ship_type_label(30) == "FISHING"
    assert _ship_type_label(31) == "TOWING"
    assert _ship_type_label(35) == "MILITARY"
    assert _ship_type_label(51) == "SAR"
    assert _ship_type_label(52) == "TUG"
    assert _ship_type_label(54) == "ANTI_POLLUTION"
    assert _ship_type_label(55) == "LAW_ENFORCEMENT"
    assert _ship_type_label(58) == "MEDICAL_TRANSPORT"
