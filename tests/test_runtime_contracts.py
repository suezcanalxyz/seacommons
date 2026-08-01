from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "docs" / "contracts"


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _environment() -> dict:
    return {
        "schema_version": "environment-snapshot/v1",
        "snapshot_id": "env_test001",
        "generated_at": "2026-08-01T10:00:00Z",
        "observed_at": "2026-08-01T10:00:00Z",
        "origin": {"lat": 37.5, "lon": 15.1},
        "crs": "EPSG:4326",
        "sources": [{
            "provider": "Open-Meteo",
            "product": "weather + marine best match",
            "retrieved_at": "2026-08-01T10:00:00Z",
            "attribution": "Open-Meteo weather and marine APIs",
        }],
        "frames": [{
            "time_utc": "2026-08-01T10:00:00Z",
            "wind": {"speed_m_s": 5.2, "direction_deg": 270, "direction_convention": "from"},
            "current": {"speed_m_s": 0.2, "direction_deg": 90, "direction_convention": "to"},
            "waves": {
                "significant_height_m": 0.8,
                "period_s": 5.6,
                "direction_deg": 260,
                "direction_convention": "from",
            },
        }],
    }


def test_environment_snapshot_contract() -> None:
    Draft202012Validator(
        _load("environment-snapshot-v1.schema.json"),
        format_checker=FormatChecker(),
    ).validate(_environment())


def test_scenario_v2_contract() -> None:
    schema = _load("scenario-v2.schema.json")
    # Inline the local reference so the test is independent from remote URI
    # retrieval and validates the exact file shipped in this repository.
    schema["properties"]["environment_snapshot"] = _load(
        "environment-snapshot-v1.schema.json"
    )
    scenario = {
        "schema_version": "scenario/v2",
        "scenario_id": "scenario-test-001",
        "created_at": "2026-08-01T10:00:00Z",
        "updated_at": "2026-08-01T10:00:01Z",
        "observed_at": "2026-08-01T10:00:00Z",
        "origin": {"type": "Point", "coordinates": [15.1, 37.5], "crs": "EPSG:4326"},
        "subject": {"kind": "life_raft", "persons": 4, "anonymous": True},
        "classification": {"scenario_type": "distress", "risk_level": "high"},
        "environment_snapshot": _environment(),
        "simulation": {
            "engine": "seacommons-browser",
            "engine_version": "0.1.0",
            "status": "completed",
            "computed_at": "2026-08-01T10:00:01Z",
            "input_hash": "env_test001:42",
            "seed": 42,
            "live_feed": True,
            "operational_use": False,
            "products": {"drift_geojson": {"type": "FeatureCollection", "features": []}},
        },
        "features": [],
        "evidence": [],
        "rendering": {
            "preferred_renderer": "cesium-web",
            "compatible_renderers": ["cesium-web", "unreal-pixel-streaming"],
        },
    }
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(scenario)


def test_drift_scene_accepts_browser_live_field_adapter() -> None:
    schema = _load("drift-scene-v1.schema.json")
    assert "browser-live-fields" in schema["properties"]["simulation"]["properties"]["engine"]["enum"]
    assert "model-estimate" in schema["properties"]["simulation"]["properties"]["status"]["enum"]
