from __future__ import annotations

from datetime import datetime, timezone

import pytest
from core.drift.opendrift_pool import (
    _representative_path,
    _speed_to_ms,
    _surface_stokes_speed,
    _trajectory_properties,
    _vector_components,
)
from core.live.projection import _is_publishable_live_drift


class _Matrix:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows
        self.shape = (len(rows), len(rows[0]))

    def __getitem__(self, key):
        rows, column = key
        assert rows == slice(None)
        return [row[column] for row in self._rows]


class _Variable:
    def __init__(self, rows: list[list[float]]) -> None:
        self.values = _Matrix(rows)


class _Dataset:
    def __init__(self, lons: list[list[float]], lats: list[list[float]]) -> None:
        self.lon = _Variable(lons)
        self.lat = _Variable(lats)


def test_representative_path_preserves_all_times_and_handles_antimeridian() -> None:
    dataset = _Dataset(
        [[179.8, 179.9, -179.9], [-179.8, -179.9, -179.7]],
        [[35.0, 35.1, 35.2], [35.2, 35.3, 35.4]],
    )

    coordinates, indices = _representative_path(dataset)

    assert indices == [0, 1, 2]
    assert len(coordinates) == 3
    assert abs(abs(coordinates[0][0]) - 180) < 0.3
    assert abs(abs(coordinates[2][0]) - 180) < 0.3


def test_trajectory_properties_include_physical_speed_time_and_curvature() -> None:
    coordinates = [[14.0, 35.0], [14.01, 35.0], [14.01, 35.01]]
    properties = _trajectory_properties(
        coordinates,
        datetime(2026, 7, 28, 12, tzinfo=timezone.utc),
        1800,
    )

    assert properties["sample_count"] == 3
    assert len(properties["timestamps_utc"]) == 3
    assert len(properties["speed_ms"]) == 3
    assert properties["distance_m"] > 1_900
    assert properties["mean_speed_ms"] > 0
    assert properties["course_deg"][1] != pytest.approx(
        properties["course_deg"][2], abs=10
    )


def test_forcing_units_and_direction_are_converted_to_opendrift_vectors() -> None:
    # A westerly wind comes from 270 degrees and therefore blows east.
    wind_east, wind_north = _vector_components(10, 270, direction_is_from=True)
    assert wind_east == pytest.approx(10)
    assert wind_north == pytest.approx(0, abs=1e-10)

    # Open-Meteo marine currents follow the direction of flow.
    current_east, current_north = _vector_components(_speed_to_ms(3.6, "km/h"), 90)
    assert current_east == pytest.approx(1)
    assert current_north == pytest.approx(0, abs=1e-10)


def test_surface_stokes_speed_is_bounded_and_zero_without_wave_data() -> None:
    # No wave data -> no fabricated Stokes drift.
    assert _surface_stokes_speed(0.0, 0.0) == 0.0
    assert _surface_stokes_speed(1.5, 0.0) == 0.0
    # Realistic Med sea state.
    moderate = _surface_stokes_speed(1.5, 6.0)
    assert 0.03 < moderate < 0.12
    # Steep short waves would over-predict monochromatic Stokes; it is clamped.
    assert _surface_stokes_speed(8.0, 4.0) == pytest.approx(0.35)
    # Longer period at the same height gives a weaker surface Stokes drift.
    assert _surface_stokes_speed(2.0, 10.0) < _surface_stokes_speed(2.0, 6.0)


def test_live_only_publishes_spatiotemporal_opendrift_with_speed_samples() -> None:
    trajectory = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[14.0, 35.0], [14.01, 35.01]],
        },
        "properties": {
            "timestamps_utc": ["2026-07-28T12:00:00Z", "2026-07-28T13:00:00Z"],
            "speed_ms": [0.4, 0.42],
        },
    }
    verified = {
        "status": "completed",
        "trajectory": trajectory,
        "metadata": {
            "model": "OpenDrift Leeway",
            "forcing_quality": "spatiotemporal",
            "operational_use": True,
        },
    }

    assert _is_publishable_live_drift(verified) is True

    degraded = {
        **verified,
        "metadata": {
            "model": "degraded demonstration fallback",
            "forcing_quality": "degraded-constant",
            "operational_use": False,
        },
    }
    assert _is_publishable_live_drift(degraded) is False
