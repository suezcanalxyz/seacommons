from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from core.rendering.scene import build_drift_scene


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "docs" / "contracts" / "drift-scene-v1.schema.json").read_text(encoding="utf-8")
)


def _event() -> dict:
    return {
        "lat": 35.52,
        "lon": 14.08,
        "timestamp": "2026-07-29T08:00:00+00:00",
        "persons": 38,
        "vessel_type": "rubber_boat",
        "domain": "ocean_sar",
    }


def _drift() -> dict:
    return {
        "status": "completed",
        "trajectory": {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[14.08, 35.52], [14.12, 35.56]],
            },
            "properties": {
                "type": "trajectory",
                "timestamps_utc": [
                    "2026-07-29T08:00:00+00:00",
                    "2026-07-29T09:00:00+00:00",
                ],
            },
        },
        "cone_6h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}},
        "cone_12h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}},
        "cone_24h": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}},
        "metadata": {
            "model": "OpenDrift Leeway 1.13",
            "start_time": "2026-07-29T08:00:00+00:00",
            "duration_h": 24,
            "scene_environment": {
                "observed_at": "2026-07-29T07:55:00+00:00",
                "wind": {
                    "speed_m_s": 7.2,
                    "direction_deg": 290,
                    "direction_convention": "from",
                    "source": "Open-Meteo",
                },
                "current": {
                    "speed_m_s": 0.31,
                    "direction_deg": 115,
                    "direction_convention": "to",
                    "source": "Open-Meteo Marine",
                },
                "waves": {
                    "significant_height_m": 1.4,
                    "period_s": 6.8,
                    "direction_deg": 305,
                    "direction_convention": "from",
                    "direction_source": "directional-wave-product",
                },
            },
        },
    }


def _validate(scene: dict) -> None:
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    validator.validate(scene)


def test_build_drift_scene_preserves_environment_and_sampled_times():
    scene = build_drift_scene(
        "scenario-001",
        _event(),
        _drift(),
        generated_at=datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc),
    )

    _validate(scene)
    assert scene["simulation"]["engine"] == "opendrift"
    assert scene["subject"] == {
        "kind": "raft",
        "persons": 38,
        "anonymous": True,
    }
    assert scene["environment"]["waves"]["significant_height_m"] == 1.4
    assert scene["trajectory"]["positions"][1]["coordinates"] == [14.12, 35.56, 0.0]
    assert scene["rendering"]["interpolation"] == "sampled-position"
    assert scene["rendering"]["people_per_cube"] == 2
    assert len(scene["uncertainty"]["features"]) == 3


def test_build_drift_scene_labels_missing_environment_as_assumption():
    drift = _drift()
    drift["trajectory"]["properties"] = {"type": "trajectory", "degraded": True}
    drift["metadata"] = {
        "model": "degraded demonstration fallback",
        "start_time": "2026-07-29T08:00:00+00:00",
        "duration_h": 12,
        "forcing": {
            "x_wind": 4,
            "y_wind": 0,
            "x_sea_water_velocity": 0,
            "y_sea_water_velocity": 0.2,
        },
    }

    scene = build_drift_scene("scenario-002", _event(), drift)

    _validate(scene)
    assert scene["simulation"]["engine"] == "deterministic-fallback"
    assert scene["simulation"]["status"] == "degraded"
    assert scene["environment"]["waves"]["direction_source"] == "scenario-assumption"
    assert scene["environment"]["wind"]["direction_convention"] == "from"
    assert scene["rendering"]["interpolation"] == "linear"
