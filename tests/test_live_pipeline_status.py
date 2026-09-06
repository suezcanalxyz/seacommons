from __future__ import annotations

from fastapi.testclient import TestClient


def test_live_pipeline_endpoint_is_public_and_uses_unified_source_families(monkeypatch):
    from core.api.main import app
    from core.acquisition import status as acquisition_status

    acquisition_status._reset_acquisition_status_for_tests()
    monkeypatch.setattr(acquisition_status, "ensure_default_acquisition_status", lambda: None)
    acquisition_status.register_acquisition_status(
        "ais", "AIS", lambda: {"state": "live", "mode": "legacy", "secret": "no"}
    )
    acquisition_status.register_acquisition_status(
        "first_party", "First-party feeds", lambda: {"state": "live"}
    )
    acquisition_status.register_acquisition_status(
        "public_feed", "Public feeds", lambda: {"state": "degraded"}
    )
    acquisition_status.register_acquisition_status(
        "partner", "Partner inputs", lambda: {"state": "offline"}
    )
    acquisition_status.register_acquisition_status(
        "radio",
        "Radio",
        lambda: {
            "state": "live",
            "configured": 1,
            "receivers": [
                {
                    "receiver_id": "med_dsc",
                    "station_label": "Mediterranean DSC",
                    "provider": "kiwisdr",
                    "state": "connected",
                    "channel_kind": "dsc",
                    "frequency_hz": 2_187_500,
                    "mode": "usb",
                    "last_observation_at": "2026-09-07T00:00:00+00:00",
                    "observations_received": 4,
                    "frontend_url": "https://secret.example.org",
                    "source_terms": "private terms",
                    "physical_lineage": "private-lineage",
                }
            ],
        },
    )

    response = TestClient(app).get("/api/v1/live/pipeline")
    assert response.status_code == 200
    payload = response.json()
    families = {source["family"] for source in payload["sources"]}
    assert families == {"ais", "first_party", "public_feed", "partner", "radio"}
    assert next(source for source in payload["sources"] if source["family"] == "ais")["mode"] == "legacy"
    radio = next(source for source in payload["sources"] if source["family"] == "radio")
    assert radio["receivers"][0]["station_label"] == "Mediterranean DSC"
    serialized = str(payload).lower()
    for forbidden in (
        "frontend_url", "source_terms", "session_id", "physical_lineage",
        "private-lineage", "secret.example.org", "private terms",
        "mmsi", "imo", "callsign", "transcript", "raw_payload",
    ):
        assert forbidden not in serialized


def test_acquisition_status_fails_closed_on_bad_provider_state(monkeypatch):
    from core.acquisition import status as acquisition_status

    acquisition_status._reset_acquisition_status_for_tests()
    acquisition_status.register_acquisition_status(
        "radio", "Radio", lambda: {"state": "invented", "frontend_url": "https://secret"}
    )
    sources = acquisition_status.acquisition_status_sources()
    assert sources == [{"family": "radio", "label": "Radio", "state": "degraded"}]
