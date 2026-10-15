from __future__ import annotations

from fastapi.testclient import TestClient


def test_operator_ingestion_gateway_fails_closed_without_secret(monkeypatch):
    from core.api.main import app
    from core.config import config

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    response = TestClient(app).get("/api/v1/operator/ingestion/overview")
    assert response.status_code == 401


def test_internal_proxy_secret_does_not_unlock_operator_ingestion(monkeypatch):
    from core.api.main import app
    from core.config import config

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    monkeypatch.setattr(config, "INTERNAL_PROXY_SECRET", "internal-secret")
    response = TestClient(app).get(
        "/api/v1/operator/ingestion/overview",
        headers={"x-seacommons-internal": "internal-secret"},
    )
    assert response.status_code == 401


def test_operator_ingestion_overview_works_with_gateway_secret(monkeypatch):
    from core.api.main import app
    from core.config import config

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    response = TestClient(app).get(
        "/api/v1/operator/ingestion/overview?hours=24",
        headers={"x-seacommons-operator-gateway": "operator-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert set(payload["counts"]) == {
        "source_observations",
        "parsed_events",
        "ingested_signals",
    }
    assert "acquisition" in payload
    assert "sources" in payload


def test_operator_observation_surface_never_claims_inline_raw_payload(monkeypatch):
    from core.api.main import app
    from core.config import config

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    response = TestClient(app).get(
        "/api/v1/operator/ingestion/observations?limit=10",
        headers={"x-seacommons-operator-gateway": "operator-secret"},
    )
    assert response.status_code == 200
    for row in response.json()["observations"]:
        assert "raw_payload" not in row
        assert "raw_payload_hash" in row
        assert "raw_payload_ref" in row


def test_operator_funnel_exposes_full_evidence_ladder(monkeypatch):
    from core.api.main import app
    from core.config import config

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    response = TestClient(app).get(
        "/api/v1/operator/ingestion/funnel?hours=24",
        headers={"x-seacommons-operator-gateway": "operator-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert [stage["id"] for stage in payload["stages"]] == [
        "raw", "normalized", "derived", "episodes", "hypotheses",
        "corroborated", "review_ready", "live",
    ]
    assert "hypothesis_states" in payload["diagnostics"]
    assert "episode_verification" in payload["diagnostics"]
    hypotheses = next(stage for stage in payload["stages"] if stage["id"] == "hypotheses")
    assert hypotheses["label"] == "Active hypotheses"
    assert "expired_or_rejected_hypotheses_excluded" in payload["diagnostics"]


def test_operator_funnel_does_not_count_expiry_housekeeping_as_recent_hypothesis(monkeypatch):
    from datetime import datetime, timezone

    import core.api.routes.operator_ingestion as operator_route
    from core.api.main import app
    from core.config import config
    from core.db.models import InvestigationHypothesisDB
    from core.db.session import session_scope

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    client = TestClient(app)
    headers = {"x-seacommons-operator-gateway": "operator-secret"}

    operator_route._fast_cache.clear()
    baseline = client.get(
        "/api/v1/operator/ingestion/funnel?hours=24", headers=headers
    ).json()
    baseline_count = next(
        stage["count"] for stage in baseline["stages"] if stage["id"] == "hypotheses"
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ids = ("test-active-hypothesis-24h", "test-expired-hypothesis-24h")
    with session_scope() as db:
        db.query(InvestigationHypothesisDB).filter(
            InvestigationHypothesisDB.hypothesis_id.in_(ids)
        ).delete(synchronize_session=False)
        for hypothesis_id, state in zip(ids, ("candidate", "expired"), strict=True):
            db.add(InvestigationHypothesisDB(
                hypothesis_id=hypothesis_id,
                hypothesis_type="dark_transit",
                subject_ids=["subj:test"],
                state=state,
                reason_codes=["gap"],
                counter_indicators=[],
                evidence_links=["event:test"],
                evidence_stage="derived",
                created_at=now,
                updated_at=now,
            ))
    try:
        operator_route._fast_cache.clear()
        payload = client.get(
            "/api/v1/operator/ingestion/funnel?hours=24", headers=headers
        ).json()
        count = next(
            stage["count"] for stage in payload["stages"] if stage["id"] == "hypotheses"
        )
        assert count == baseline_count + 1
        assert payload["diagnostics"]["expired_or_rejected_hypotheses_excluded"] >= 1
    finally:
        with session_scope() as db:
            db.query(InvestigationHypothesisDB).filter(
                InvestigationHypothesisDB.hypothesis_id.in_(ids)
            ).delete(synchronize_session=False)
        operator_route._fast_cache.clear()


def test_operator_pipeline_map_documents_gap_semantics(monkeypatch):
    from core.api.main import app
    from core.config import config

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    response = TestClient(app).get(
        "/api/v1/operator/ingestion/pipeline-map",
        headers={"x-seacommons-operator-gateway": "operator-secret"},
    )
    assert response.status_code == 200
    chains = response.json()["chains"]
    ais = next(chain for chain in chains if chain["id"] == "ais_position_integrity")
    assert any("reappearance" in value for value in ais["raw_observations"])
    assert any("canonical dark-gap detector" in value for value in ais["derived_processors"])


def test_operator_case_surface_labels_hypotheses_not_illegality_findings(monkeypatch):
    from core.api.main import app
    from core.config import config

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    response = TestClient(app).get(
        "/api/v1/operator/ingestion/cases?limit=5",
        headers={"x-seacommons-operator-gateway": "operator-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "not findings of illegality" in payload["note"].lower()
    for case in payload["cases"]:
        assert "illegal_activity_status" in case
        assert "evidence" in case
        assert "blockers" in case


def test_operator_funnel_excludes_legacy_unclassified_from_corroborated(monkeypatch):
    from datetime import datetime, timezone

    import core.api.routes.operator_ingestion as operator_route
    from core.api.main import app
    from core.config import config
    from core.db.models import MaritimeEpisodeDB
    from core.db.session import session_scope

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    operator_route._fast_cache.clear()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as db:
        for episode_id, family in (
            ("recognized-corrob", "dark_transit_episode"),
            ("legacy-unclassified-corrob", "unclassified_episode"),
        ):
            db.add(MaritimeEpisodeDB(
                episode_id=episode_id,
                episode_family=family,
                subject_ids=["211000001"],
                start_at=now,
                end_at=now,
                geometry={"type": "Point", "coordinates": [14.5, 35.9]},
                observation_ids=["obs-1", "obs-2"],
                feature_ids=["event-1", "event-2"],
                independence_groups=["ais_sensor_lineage", "satellite_sensor_lineage"],
                verification_status="multi_source_corroborated",
                behaviour_context={},
                alternative_explanations=[],
                evidence_fingerprint=episode_id,
                method_version="test",
                status="active",
                updated_at=now,
            ))

    response = TestClient(app).get(
        "/api/v1/operator/ingestion/funnel?hours=24",
        headers={"x-seacommons-operator-gateway": "operator-secret"},
    )
    assert response.status_code == 200
    stages = {stage["id"]: stage["count"] for stage in response.json()["stages"]}
    assert stages["episodes"] == 1
    assert stages["corroborated"] == 1


def test_operator_overall_exposes_all_time_corpus(monkeypatch):
    import core.api.routes.operator_ingestion as operator_route
    from core.api.main import app
    from core.config import config

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    operator_route._overall_cache = None
    response = TestClient(app).get(
        "/api/v1/operator/ingestion/overall",
        headers={"x-seacommons-operator-gateway": "operator-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "all_time"
    assert [stage["id"] for stage in payload["stages"]] == [
        "raw", "normalized", "derived", "episodes", "hypotheses",
        "corroborated", "review_ready",
    ]
    assert set(payload["sensor_activity"]) >= {
        "ais_fixes", "radio_bursts", "radio_events", "satellite_observations", "source_names",
    }
    assert set(payload["breakdowns"]) >= {
        "raw_by_source", "raw_observation_types", "normalized_event_types",
        "episode_families", "hypothesis_types", "hypothesis_states",
    }


def test_futures_operator_bearer_reuses_canonical_ingestion_without_gateway_secret(monkeypatch):
    """An authenticated operator can read the same canonical API from Futures."""
    from core.api.main import app
    from core.config import config
    from core.security import Principal
    import core.security as security

    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    monkeypatch.setattr(
        security, "require_futures_identity",
        lambda request: Principal(subject="operator-test", roles=frozenset({"futures_viewer"}), claims={}),
    )
    result = TestClient(app).get(
        "/api/v1/operator/ingestion/overview?hours=24",
        headers={"Authorization": "Bearer verified-by-test-jwt"},
    )
    assert result.status_code == 200
    assert "source_observations" in result.json()["counts"]


def test_futures_authenticated_viewer_can_read_intelligence(monkeypatch):
    """Every authenticated Futures viewer sees the same Intelligence metrics."""
    from core.api.main import app
    from core.config import config
    from core.security import Principal
    import core.security as security

    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    monkeypatch.setattr(
        security, "require_futures_identity",
        lambda request: Principal(subject="viewer-test", roles=frozenset({"futures_viewer"}), claims={}),
    )
    result = TestClient(app).get(
        "/api/v1/operator/ingestion/observations?limit=5",
        headers={"Authorization": "Bearer verified-by-test-jwt"},
    )
    assert result.status_code == 200


def test_futures_invalid_bearer_fails_closed(monkeypatch):
    from core.api.main import app
    from core.config import config
    import core.security as security
    from fastapi import HTTPException

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    def invalid_session(_request):
        raise HTTPException(status_code=401, detail="Invalid Futures session")
    monkeypatch.setattr(security, "require_futures_identity", invalid_session)
    response = TestClient(app).get(
        "/api/v1/operator/ingestion/overview?hours=24",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


def test_measurement_contract_explains_clocks_and_separates_created_updated(monkeypatch):
    from core.api.main import app
    from core.config import config

    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    response = TestClient(app).get(
        "/api/v1/operator/ingestion/measurements?hours=24",
        headers={"x-seacommons-operator-gateway": "operator-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == 1
    assert payload["window_hours"] == 24
    assert payload["scope"] == "rolling"
    assert payload["counts"]["investigations_created"] <= payload["counts"]["investigations_updated"] + payload["counts"]["investigations_open_now"]
    assert payload["definitions"]["investigations_created"]["clock"] == "created_at"
    assert payload["definitions"]["investigations_updated"]["clock"] == "updated_at"
    assert payload["definitions"]["ais_positions_received"]["clock"] == "received_at"
    assert payload["definitions"]["ais_positions_observed"]["clock"] == "ts"
    assert payload["definitions"]["investigations_open_now"]["clock"] == "current state"


def test_measurement_contract_rejects_unauthenticated_access(monkeypatch):
    from core.api.main import app
    from core.config import config
    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "operator-secret")
    response = TestClient(app).get("/api/v1/operator/ingestion/measurements?hours=24")
    assert response.status_code == 401


def test_futures_readonly_agent_snapshot(monkeypatch, tmp_path):
    import json
    from core.api.main import app
    from core.config import config

    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({
        "synced_at": "2026-10-14T13:48:33Z",
        "tasks": [{
            "title": "SeaCommons Forensic Repair Loop",
            "enabled": True, "cadence": "Every 3 hours",
            "last_run": "2026-10-14T13:48:10Z", "timezone": "Europe/Rome",
            "prompt": "PRIVATE NEVER FORWARD",
        }],
    }))
    monkeypatch.setenv("SEACOMMONS_FUTURES_TASK_SNAPSHOT", str(tasks_file))
    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "test-gateway")
    client = TestClient(app)
    assert client.get("/api/v1/operator/ingestion/scheduled-tasks").status_code == 401
    result = client.get("/api/v1/operator/ingestion/scheduled-tasks", headers={"x-seacommons-operator-gateway": "test-gateway"})
    assert result.status_code == 200
    assert result.json()["live_sync"] is False
    assert result.json()["tasks"][0]["title"] == "SeaCommons Forensic Repair Loop"
    assert "prompt" not in result.json()["tasks"][0]


def test_overall_metrics_has_all_twelve_headline_measurements(monkeypatch):
    from core.api.main import app
    from core.config import config
    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "test-gateway")
    client = TestClient(app)
    assert client.get("/api/v1/operator/ingestion/overall-metrics").status_code == 401
    result = client.get("/api/v1/operator/ingestion/overall-metrics", headers={"x-seacommons-operator-gateway": "test-gateway"})
    assert result.status_code == 200
    payload = result.json()
    assert payload["scope"] == "all_time"
    assert len(payload["stages"]) == 7
    for key in ("ais_fixes", "radio_bursts", "radio_events", "satellite_observations", "source_names"):
        assert key in payload["sensor_activity"]


def test_futures_audience_accepts_only_configured_oidc_client(monkeypatch):
    from core import security
    monkeypatch.setenv("SEACOMMONS_FUTURES_OIDC_CLIENT_ID", "test-authorized-client")
    assert security._futures_audiences() == ["authenticated", "test-authorized-client"]
    monkeypatch.setenv("SEACOMMONS_FUTURES_OIDC_CLIENT_ID", "another-authorized-client")
    assert "test-authorized-client" not in security._futures_audiences()
    assert "another-authorized-client" in security._futures_audiences()


def test_public_intelligence_overall_is_aggregate_only_and_keeps_private_route_closed(monkeypatch):
    from core.api.main import app
    from core.api.routes import operator_ingestion
    from core.config import config
    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "test-gateway")
    monkeypatch.setattr(operator_ingestion, "_overall_metrics_aggregate", lambda:{
        "scope":"all_time", "generated_at":"2026-10-15T16:00:00+00:00",
        "stages":[{"id":name,"count":index+5} for index,name in enumerate((
          "raw","normalized","derived","episodes","hypotheses","corroborated","review_ready"))],
        "sensor_activity":{"ais_fixes":530,"radio_bursts":20,"radio_events":4,
            "satellite_observations":6,"source_names":3,"extra_unpublished_field":999},
        "estimated_fields":["ais_fixes"],"unavailable_fields":[],
        "extra_unpublished_data":{"identifier":"not included"},
    })
    client=TestClient(app)
    response=client.get("/api/v1/futures/intelligence-overall")
    assert response.status_code==200
    data=response.json()
    assert data["access"]=="public_aggregate"
    assert len(data["stages"])==7
    assert set(data["sensor_activity"])=={"ais_fixes","radio_bursts","radio_events","satellite_observations","source_names"}
    assert data["estimated_fields"]==["ais_fixes"]
    assert "extra_unpublished_data" not in data
    assert "extra_unpublished_field" not in data["sensor_activity"]
    assert client.get("/api/v1/operator/ingestion/overall-metrics").status_code==401
