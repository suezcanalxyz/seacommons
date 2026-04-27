from __future__ import annotations

import os

os.environ["MOCK"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///./core/data/test_pilot_smoke.db"
os.environ["SUEZCANAL_SIGNING_KEY"] = "1111111111111111111111111111111111111111111111111111111111111111"

from fastapi.testclient import TestClient

from core.api.main import app
from core.db.session import init_database


init_database()
client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_ops_summary() -> None:
    response = client.get("/api/v1/ops/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["product"]["name"] == "Seacommons"
    assert "backend" in data
    assert "traffic" in data
    assert "sar" in data


def test_alert_lifecycle_and_forensic() -> None:
    payload = {
        "lat": 35.123,
        "lon": 15.456,
        "timestamp": "2026-03-21T12:00:00Z",
        "persons": 45,
        "vessel_type": "rubber_boat",
        "domain": "ballistic",
    }
    create = client.post("/api/v1/alert", json=payload)
    assert create.status_code == 200
    event_id = create.json()["event_id"]

    fetch = client.get(f"/api/v1/alert/{event_id}")
    assert fetch.status_code == 200
    alert = fetch.json()
    assert alert["status"] in {"processing", "completed"}

    forensic = client.get(f"/api/v1/forensic/{event_id}")
    assert forensic.status_code == 200

    verify = client.get(f"/api/v1/forensic/{event_id}/verify")
    assert verify.status_code == 200
    verified = verify.json()
    assert verified["hash_match"] is True


def test_sar_requires_real_opendrift() -> None:
    payload = {
        "lat": 35.123,
        "lon": 15.456,
        "timestamp": "2026-03-21T12:00:00Z",
        "persons": 45,
        "vessel_type": "rubber_boat",
        "domain": "ocean_sar",
    }
    create = client.post("/api/v1/alert", json=payload)
    assert create.status_code == 200
    event_id = create.json()["event_id"]

    fetch = client.get(f"/api/v1/alert/{event_id}")
    assert fetch.status_code == 200
    assert fetch.json()["status"] == "failed"

    geojson = client.get(f"/api/v1/alert/{event_id}/geojson")
    assert geojson.status_code == 500
