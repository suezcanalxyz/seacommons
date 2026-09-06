from datetime import datetime, timezone


def test_operator_baseline_route_is_not_public():
    from fastapi.testclient import TestClient
    from core.api.main import app
    from core.config import config

    client = TestClient(app)
    previous = config.AUTH_ENABLED
    config.AUTH_ENABLED = True
    try:
        response = client.get("/api/v1/mda/vessel/229113000/baseline")
        assert response.status_code == 401
    finally:
        config.AUTH_ENABLED = previous


def test_public_live_vessel_context_does_not_request_internal_behaviour(monkeypatch):
    from fastapi.testclient import TestClient
    from core.api.main import app
    from core.api.routes import mda

    called = {}

    def fake_dossier(mmsi, *, hours, track_limit=5000, include_behaviour=False):
        called["include_behaviour"] = include_behaviour
        return {"mmsi": mmsi, "static": {}, "track": {"type": "FeatureCollection", "features": []}, "track_points": [], "recent_port_calls": []}

    monkeypatch.setattr(mda, "build_vessel_dossier", fake_dossier)
    response = TestClient(app).get("/api/v1/live/vessels/229113000/context")
    assert response.status_code == 200
    assert called["include_behaviour"] is False
    assert "behaviour_assessment" not in response.json()
    assert "context" not in response.json()


def test_detector_behaviour_context_is_advisory(monkeypatch):
    from core.mda import watch

    class Assessment:
        status = "unusual"
        baseline_id = "vbl:test"
        method_version = "vessel-behaviour-v1"
        reason_codes = ("ROUTE_DEVIATION",)
        dimensions = {"route": {"status": "unusual", "distance_nm": 20.0, "threshold_nm": 8.0}}
        caveats = ()
        evaluated_at = datetime.now(timezone.utc)

    monkeypatch.setattr(watch, "_latest_behavioural_baseline", lambda mmsi: object())
    monkeypatch.setattr(watch, "_recent_track_for_behaviour", lambda mmsi: [{"lat": 35.0, "lon": 14.0, "ts": "2026-09-06T00:00:00+00:00", "sog": 12.0}])
    monkeypatch.setattr(watch, "_assess_behaviour", lambda track, baseline: Assessment())

    result = watch._behaviour_context_for("229113000")
    assert result["status"] == "unusual"
    assert result["reason_codes"] == ["ROUTE_DEVIATION"]
    assert "open_case" not in result
    assert "publication_status" not in result
