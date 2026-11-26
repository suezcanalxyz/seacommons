"""Synthetic contracts for archived message aggregates."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from core.intel.historical_snapshot import public_snapshot, validate_snapshot


@pytest.fixture
def snapshot():
    return {
        "method": "historical-observation-profile/v2", "manifest_sha256": "a" * 64,
        "sample_bytes": 1024, "status": "incomplete",
        "tables": {
            "vessel_tracks": {
                "sample_parts": 1, "total_parts": 2, "sample_rows": 50, "total_rows": 100,
                "multi_month_parts": 0, "time_quality": {"naive": 50},
                "calendar_months": {"naive:2026-01": 50},
                "reported_sog_knots": {"zero_or_imputed_missing": 50},
            },
            "source_observations": {
                "sample_parts": 1, "total_parts": 2, "sample_rows": 50, "total_rows": 100,
                "multi_month_parts": 0, "time_quality": {"explicit_offset": 50},
                "calendar_months": {"explicit_offset:2026-01": 50},
            },
        },
    }


def test_valid_snapshot(snapshot):
    validate_snapshot(snapshot)


@pytest.mark.parametrize(("path", "value"), [
    (("method",), "unknown"), (("manifest_sha256",), "private/path"),
    (("status",), "complete"), (("sample_bytes",), True), (("sample_bytes",), 2**27),
    (("tables", "vessel_tracks", "sample_parts"), 17),
    (("tables", "vessel_tracks", "total_parts"), 0),
    (("tables", "vessel_tracks", "sample_rows"), -1),
    (("tables", "vessel_tracks", "sample_rows"), 50.0),
    (("tables", "vessel_tracks", "total_rows"), 49),
    (("tables", "vessel_tracks", "total_rows"), 50),
    (("tables", "vessel_tracks", "time_quality"), {"naive": 50, "explicit_offset": 1}),
    (("tables", "vessel_tracks", "calendar_months"), {"explicit_offset:2026-01": 50}),
    (("tables", "vessel_tracks", "calendar_months"), {"naive:2026-13": 50}),
    (("tables", "vessel_tracks", "reported_sog_knots"), {"zero": 50}),
    (("tables", "source_observations", "mmsi"), "secret"),
    (("tables", "source_observations", "calendar_months"), {"secret": 50}),
    (("tables", "source_observations", "reported_sog_knots"), {}),
])
def test_rejects_invalid_snapshot(snapshot, path, value):
    invalid = deepcopy(snapshot)
    parent = invalid
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises(ValueError):
        validate_snapshot(invalid)


def test_projection_requires_exact_approval_and_withholds_sparse_cells(snapshot, tmp_path):
    table = snapshot["tables"]["vessel_tracks"]
    table["calendar_months"] = {"naive:2026-01": 49, "naive:2026-02": 1}
    payload = json.dumps(snapshot).encode()
    path = tmp_path / "private.json"
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    public = public_snapshot(path, digest)
    assert "manifest_sha256" not in public and "sample_bytes" not in public
    assert public["tables"]["vessel_tracks"]["calendar_months"] is None
    assert public["tables"]["vessel_tracks"]["time_quality"] is None
    assert public["tables"]["vessel_tracks"]["reported_sog_knots"] == {"zero_or_imputed_missing": 50}
    assert public["tables"]["source_observations"]["calendar_months"] == {"explicit_offset:2026-01": 50}
    path.write_bytes(payload + b" ")
    with pytest.raises(ValueError, match="publication approval"):
        public_snapshot(path, digest)


def test_projection_withholds_denominator_that_reveals_sparse_remainder(snapshot, tmp_path):
    snapshot["tables"]["vessel_tracks"]["total_rows"] = 55
    payload = json.dumps(snapshot).encode()
    path = tmp_path / "private.json"
    path.write_bytes(payload)
    public = public_snapshot(path, hashlib.sha256(payload).hexdigest())
    assert public["tables"]["vessel_tracks"]["sample_rows"] == 50
    assert public["tables"]["vessel_tracks"]["total_rows"] is None
    assert public["tables"]["source_observations"]["total_rows"] == 100


def test_play_route_fails_closed_and_serves_reviewed_projection(snapshot, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from core.api.routes.play import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    path = tmp_path / "private.json"
    payload = json.dumps(snapshot).encode()
    path.write_bytes(payload)
    monkeypatch.setenv("PLAY_ANALYTICS_SNAPSHOT_PATH", str(path))
    monkeypatch.delenv("PLAY_ANALYTICS_APPROVED_SHA256", raising=False)
    unavailable = client.get("/api/v1/play/analytics")
    assert unavailable.status_code == 503
    assert unavailable.json() == {"status": "unavailable"}
    monkeypatch.setenv("PLAY_ANALYTICS_APPROVED_SHA256", hashlib.sha256(payload).hexdigest())
    published = client.get("/api/v1/play/analytics")
    assert published.status_code == 200
    assert published.headers["cache-control"] == "no-store"
    assert published.json()["tables"]["vessel_tracks"]["sample_rows"] == 50
    path.write_bytes(payload + b" ")
    assert client.get("/api/v1/play/analytics").status_code == 503
