# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build the renderer-neutral drift-scene/v1 payload.

OpenDrift remains authoritative for horizontal motion and uncertainty. This
module only packages persisted simulation output for CesiumJS and Unreal.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

_MAX_RENDERED_PEOPLE = 24


def _number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _bearing_to(east: float, north: float) -> float:
    if abs(east) < 1e-12 and abs(north) < 1e-12:
        return 0.0
    return math.degrees(math.atan2(east, north)) % 360


def _iso_datetime(value: Any, fallback: datetime) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            parsed = fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _subject_kind(vessel_type: Any) -> str:
    normalized = str(vessel_type or "unknown").strip().lower()
    if normalized in {"rubber_boat", "life_raft", "raft"}:
        return "raft"
    if normalized in {"person", "person_in_water", "piw"}:
        return "person_in_water"
    if normalized in {"unknown", ""}:
        return "unknown"
    return "vessel"


def _simulation_state(drift: dict[str, Any]) -> tuple[str, str, list[str]]:
    metadata = drift.get("metadata") or {}
    trajectory = drift.get("trajectory") or {}
    properties = trajectory.get("properties") or {}
    model = str(metadata.get("model") or "").lower()
    degraded = bool(properties.get("degraded")) or "fallback" in model or "degraded" in model
    if degraded:
        return "deterministic-fallback", "degraded", ["horizontal_drift", "uncertainty"]
    return "opendrift", "operational", ["horizontal_drift", "uncertainty"]


def _fallback_environment(
    event: dict[str, Any],
    drift: dict[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    forcing = (drift.get("metadata") or {}).get("forcing") or {}
    wind_east = _number(forcing.get("x_wind"))
    wind_north = _number(forcing.get("y_wind"))
    current_east = _number(forcing.get("x_sea_water_velocity"))
    current_north = _number(forcing.get("y_sea_water_velocity"))
    wind_to = _bearing_to(wind_east, wind_north)
    wind_from = (wind_to + 180) % 360
    return {
        "observed_at": observed_at,
        "wind": {
            "speed_m_s": math.hypot(wind_east, wind_north),
            "direction_deg": wind_from,
            "direction_convention": "from",
            "source": "persisted simulation forcing",
        },
        "current": {
            "speed_m_s": math.hypot(current_east, current_north),
            "direction_deg": _bearing_to(current_east, current_north),
            "direction_convention": "to",
            "source": "persisted simulation forcing",
        },
        "waves": {
            "significant_height_m": 0.65,
            "period_s": 5.5,
            "direction_deg": wind_from,
            "direction_convention": "from",
            "direction_source": "scenario-assumption",
        },
    }


def _trajectory_positions(
    event: dict[str, Any],
    drift: dict[str, Any],
    fallback_time: datetime,
) -> tuple[list[dict[str, Any]], str]:
    trajectory = drift.get("trajectory") or {}
    coordinates = (trajectory.get("geometry") or {}).get("coordinates") or []
    coordinates = [
        point for point in coordinates
        if isinstance(point, (list, tuple)) and len(point) >= 2
    ]
    if not coordinates:
        coordinates = [[_number(event.get("lon")), _number(event.get("lat")), 0]]

    properties = trajectory.get("properties") or {}
    raw_times = properties.get("timestamps_utc") or properties.get("times") or []
    sampled = isinstance(raw_times, list) and len(raw_times) == len(coordinates)
    metadata = drift.get("metadata") or {}
    start_value = metadata.get("start_time") or event.get("timestamp")
    start = datetime.fromisoformat(
        _iso_datetime(start_value, fallback_time).replace("Z", "+00:00")
    )
    duration_hours = max(0.0, _number(metadata.get("duration_h"), 24))

    positions: list[dict[str, Any]] = []
    for index, point in enumerate(coordinates):
        if sampled:
            timestamp = _iso_datetime(raw_times[index], start)
        else:
            fraction = index / max(1, len(coordinates) - 1)
            timestamp = (start + timedelta(hours=duration_hours * fraction)).isoformat()
        positions.append({
            "time": timestamp,
            "coordinates": [
                _number(point[0]),
                _number(point[1]),
                _number(point[2]) if len(point) > 2 else 0.0,
            ],
        })
    return positions, "sampled-position" if sampled else "linear"


def build_drift_scene(
    event_id: str,
    event: dict[str, Any],
    drift: dict[str, Any],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a drift-scene/v1 document from persisted alert and drift data."""
    now = generated_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    observed_at = _iso_datetime(event.get("timestamp"), now)
    metadata = drift.get("metadata") or {}
    environment = metadata.get("scene_environment")
    if not isinstance(environment, dict):
        environment = _fallback_environment(event, drift, observed_at)

    positions, interpolation = _trajectory_positions(event, drift, now)
    engine, status, authoritative_for = _simulation_state(drift)
    persons = max(1, min(10_000, round(_number(event.get("persons"), 1))))
    uncertainty = [
        feature for feature in (
            drift.get("cone_6h"),
            drift.get("cone_12h"),
            drift.get("cone_24h"),
        )
        if isinstance(feature, dict)
    ]

    return {
        "schema_version": "drift-scene/v1",
        "scenario_id": event_id,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "simulation": {
            "engine": engine,
            "status": status,
            "authoritative_for": authoritative_for,
            "model_version": str(metadata.get("model") or engine),
        },
        "subject": {
            "kind": _subject_kind(event.get("vessel_type")),
            "persons": persons,
            "anonymous": True,
        },
        "environment": environment,
        "trajectory": {
            "crs": "EPSG:4326",
            "positions": positions,
        },
        "uncertainty": {
            "format": "geojson-feature-list",
            "features": uncertainty,
        },
        "rendering": {
            "people_per_cube": max(1, math.ceil(persons / _MAX_RENDERED_PEOPLE)),
            "vertical_motion_physical": False,
            "interpolation": interpolation,
        },
    }

