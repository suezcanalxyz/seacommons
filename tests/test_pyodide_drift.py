# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "web" / "public" / "pyodide" / "seacommons_drift.py"
SCHEMA_PATH = ROOT / "docs" / "contracts" / "drift-trajectory-v1.schema.json"

_SPEC = importlib.util.spec_from_file_location("seacommons_pyodide_drift", MODULE_PATH)
assert _SPEC and _SPEC.loader
drift = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = drift
_SPEC.loader.exec_module(drift)


def _cube(first: float, second: float | None = None) -> list[list[list[float]]]:
    later = first if second is None else second
    return [
        [[first, first], [first, first]],
        [[later, later], [later, later]],
    ]


def _request(
    *,
    model: str = "oceandrift",
    vessel_type: str = "unknown",
    current_u: tuple[float, float] = (1.0, 1.0),
    current_v: tuple[float, float] = (0.0, 0.0),
    wind_u: tuple[float, float] | None = None,
    wind_v: tuple[float, float] | None = None,
    duration_seconds: int = 3600,
    time_step_seconds: int = 900,
) -> dict:
    variables = {
        "current_u": _cube(*current_u),
        "current_v": _cube(*current_v),
    }
    if wind_u is not None and wind_v is not None:
        variables["wind_u"] = _cube(*wind_u)
        variables["wind_v"] = _cube(*wind_v)
    return {
        "lkp": {"lat": 35.0, "lon": 14.0},
        "timestamp": "2026-08-20T12:00:00Z",
        "vessel_type": vessel_type,
        "model": model,
        "duration_seconds": duration_seconds,
        "time_step_seconds": time_step_seconds,
        "output_interval_seconds": time_step_seconds,
        "netcdf": {
            "format": "decoded-grid/v1",
            "source": "test-netcdf-subset",
            "coordinates": {
                "time": ["2026-08-20T12:00:00Z", "2026-08-20T14:00:00Z"],
                "latitude": [34.0, 36.0],
                "longitude": [13.0, 15.0],
            },
            "variables": variables,
        },
    }


def _distance_m(left: list[float], right: list[float]) -> float:
    lon1, lat1 = map(math.radians, left)
    lon2, lat2 = map(math.radians, right)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * drift.EARTH_RADIUS_M * math.asin(math.sqrt(value))


def test_oceandrift_constant_current_advects_east_without_server_dependencies() -> None:
    result = drift.simulate(_request())

    assert result["type"] == "Feature"
    assert result["geometry"]["type"] == "LineString"
    assert len(result["geometry"]["coordinates"]) == 5
    start, end = result["geometry"]["coordinates"][0], result["geometry"]["coordinates"][-1]
    assert end[0] > start[0]
    assert end[1] == pytest.approx(start[1], abs=1e-5)
    assert _distance_m(start, end) == pytest.approx(3600.0, rel=2e-4)
    assert result["properties"]["operational_use"] is False


def test_leeway_uses_mean_opendrift_profile_coefficients() -> None:
    request = _request(
        model="leeway",
        vessel_type="life_raft",
        current_u=(0.0, 0.0),
        wind_u=(10.0, 10.0),
        wind_v=(0.0, 0.0),
    )

    result = drift.simulate(request)
    start, end = result["geometry"]["coordinates"][0], result["geometry"]["coordinates"][-1]

    # LIFE-RAFT-NB-1: 3.7% * 10 m/s = 0.37 m/s; symmetric mean
    # left/right crosswind coefficients cancel for the representative line.
    assert _distance_m(start, end) == pytest.approx(0.37 * 3600, rel=3e-4)
    assert end[0] > start[0]
    assert end[1] == pytest.approx(start[1], abs=1e-5)
    assert result["properties"]["leeway_object_key"] == "LIFE-RAFT-NB-1"


def test_midpoint_integrator_interpolates_time_varying_current() -> None:
    request = _request(
        current_u=(0.0, 2.0),
        duration_seconds=3600,
        time_step_seconds=3600,
    )

    result = drift.simulate(request)
    start, end = result["geometry"]["coordinates"]

    # The two forcing frames are two hours apart. At the half-hour RK2 sample
    # the interpolated current is 0.5 m/s.
    assert _distance_m(start, end) == pytest.approx(1800.0, rel=3e-4)


def test_simulate_json_is_deterministic_and_writes_only_standard_json(tmp_path: Path) -> None:
    request = _request()
    first = drift.simulate_json(json.dumps(request))
    second = drift.simulate_json(json.dumps(request))
    assert first == second
    assert math.isfinite(json.loads(first)["geometry"]["coordinates"][-1][0])

    output = tmp_path / "trajectory.json"
    drift.write_trajectory_json(request, output)
    assert json.loads(output.read_text(encoding="utf-8")) == json.loads(first)


def test_output_validates_against_trajectory_contract() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(drift.simulate(_request()))


def test_leeway_requires_local_wind_components() -> None:
    with pytest.raises(drift.DriftInputError, match="requires wind_u and wind_v"):
        drift.simulate(_request(model="leeway", vessel_type="life_raft"))


def test_trajectory_fails_closed_when_subset_is_too_small() -> None:
    request = _request(current_u=(10.0, 10.0), duration_seconds=7200)
    request["netcdf"]["coordinates"]["longitude"] = [14.0, 14.01]
    request["lkp"]["lon"] = 14.005

    with pytest.raises(drift.DriftInputError, match="left the NetCDF longitude domain"):
        drift.simulate(request)


def test_local_cf_netcdf_adapter(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    np = pytest.importorskip("numpy")
    path = tmp_path / "forcing.nc"
    with netcdf4.Dataset(path, "w") as dataset:
        dataset.createDimension("time", 2)
        dataset.createDimension("depth", 1)
        dataset.createDimension("latitude", 2)
        dataset.createDimension("longitude", 2)
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "seconds since 2026-08-20 12:00:00 +00:00"
        time[:] = [0, 7200]
        latitude = dataset.createVariable("latitude", "f8", ("latitude",))
        latitude.standard_name = "latitude"
        latitude[:] = [34.0, 36.0]
        longitude = dataset.createVariable("longitude", "f8", ("longitude",))
        longitude.standard_name = "longitude"
        longitude[:] = [13.0, 15.0]
        for name, standard_name, value in (
            ("uo", "eastward_sea_water_velocity", 1.0),
            ("vo", "northward_sea_water_velocity", 0.0),
            ("u10", "eastward_wind", 0.0),
            ("v10", "northward_wind", 0.0),
        ):
            variable = dataset.createVariable(name, "f4", ("time", "depth", "latitude", "longitude"))
            variable.standard_name = standard_name
            variable.units = "m s-1"
            variable[:] = np.full((2, 1, 2, 2), value, dtype="f4")

    request = _request()
    request["netcdf"] = {
        "format": "netcdf-cf",
        "path": str(path),
        "dimension_indices": {"depth": 0},
    }
    result = drift.simulate(request)

    assert result["properties"]["forcing"] == "local-netcdf:forcing.nc"
    assert _distance_m(
        result["geometry"]["coordinates"][0],
        result["geometry"]["coordinates"][-1],
    ) == pytest.approx(3600.0, rel=2e-4)


def test_netcdf_adapter_rejects_remote_urls() -> None:
    request = _request()
    request["netcdf"] = {
        "format": "netcdf-cf",
        "path": "https://example.org/forcing.nc",
    }

    with pytest.raises(drift.DriftInputError, match="local Pyodide filesystem"):
        drift.simulate(request)
