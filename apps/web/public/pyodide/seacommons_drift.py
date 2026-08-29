# SPDX-License-Identifier: AGPL-3.0-or-later
"""Serverless Lagrangian surface-drift kernel for Pyodide.

The numerical core uses only the Python standard library.  ``netCDF4`` and
``numpy`` are imported lazily by the local-file adapter, and both are available
as pre-built Pyodide packages.  The module never opens a URL, database, or
remote API: a browser must first materialise a small CF-NetCDF subset in the
Pyodide filesystem and pass its local path in the JSON request.

Public entry points:

``simulate(request)``
    Accept a Python mapping and return one GeoJSON trajectory mapping.

``simulate_json(request_json)``
    JSON-string bridge intended for JavaScript/Pyodide interop.

``write_trajectory_json(request, output_path)``
    Write the one and only simulation artefact to a local JSON file.

This is a deliberately small horizontal model.  It reproduces the essential
OpenDrift update pattern (sample forcing -> compute velocity -> advect) and the
mean Leeway coefficient formula, but it is not a bit-for-bit OpenDrift port and
does not implement coast interaction, vertical mixing, capsizing, or ensemble
uncertainty.  Its output is therefore a model estimate, not an authoritative
SAR product.
"""

from __future__ import annotations

import bisect
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import pairwise
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "org.seacommons.drift-trajectory/v1"
ENGINE_VERSION = "1.0.0"
EARTH_RADIUS_M = 6_371_008.8


class DriftInputError(ValueError):
    """Raised when a simulation request or forcing subset is invalid."""


@dataclass(frozen=True)
class Vector:
    east: float
    north: float

    def __add__(self, other: Vector) -> Vector:
        return Vector(self.east + other.east, self.north + other.north)

    def scale(self, factor: float) -> Vector:
        return Vector(self.east * factor, self.north * factor)

    @property
    def speed(self) -> float:
        return math.hypot(self.east, self.north)


@dataclass(frozen=True)
class LeewayProfile:
    """Deterministic mean coefficients from OpenDrift's Leeway properties.

    Slopes are percent of wind speed and offsets are centimetres per second,
    matching the OpenDrift Leeway formula.  Random coefficient perturbations
    are intentionally omitted because this kernel returns one representative
    trajectory rather than an ensemble.
    """

    object_key: str
    downwind_slope: float
    downwind_offset: float
    right_slope: float
    right_offset: float
    left_slope: float
    left_offset: float


# A compact, explicit subset of OpenDrift's 85 Leeway categories.  SeaCommons
# input names map to representative categories; adding a category is a data
# change, not a change to the numerical kernel.
LEEWAY_PROFILES: dict[str, LeewayProfile] = {
    "person_in_water": LeewayProfile("PIW-1", 0.96, 0.0, 0.54, 0.0, -0.54, 0.0),
    "life_raft": LeewayProfile("LIFE-RAFT-NB-1", 3.70, 0.0, 1.98, 0.0, -1.98, 0.0),
    # Closest explicit OpenDrift reference category for a small improvised
    # migration craft without sail.  The approximation remains visible in the
    # output through ``leeway_object_key``.
    "rubber_boat": LeewayProfile("REFUGEE-RAFT-1", 1.56, 8.30, 0.078, 2.70, -0.078, -2.70),
    "motorboat": LeewayProfile("SKIFF-1", 3.15, 0.0, 1.29, 0.0, -1.29, 0.0),
    "wooden_boat": LeewayProfile("SKIFF-2", 2.87, 3.98, 0.32, -2.93, -0.62, 1.03),
    "fishing_vessel": LeewayProfile("FISHING-VESSEL-1", 2.47, 0.0, 2.76, 0.0, -2.76, 0.0),
    "sailboat": LeewayProfile("SAILBOAT-1", 4.50, 0.0, 4.95, 0.0, -2.82, 0.0),
    "unknown": LeewayProfile("LIFE-RAFT-NB-1", 3.70, 0.0, 1.98, 0.0, -1.98, 0.0),
}

REQUIRED_COMPONENTS = ("current_u", "current_v")
WIND_COMPONENTS = ("wind_u", "wind_v")
OPTIONAL_COMPONENTS = ("stokes_u", "stokes_v")


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise DriftInputError(f"{label} must be numeric")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise DriftInputError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed):
        raise DriftInputError(f"{label} must be finite")
    return parsed


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    parsed = _finite(value, label)
    if not parsed.is_integer():
        raise DriftInputError(f"{label} must be an integer")
    result = int(parsed)
    if result < minimum or result > maximum:
        raise DriftInputError(f"{label} must be between {minimum} and {maximum}")
    return result


def _parse_time(value: Any, label: str = "timestamp") -> datetime:
    text = str(value or "").strip()
    if not text:
        raise DriftInputError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DriftInputError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise DriftInputError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso_utc(epoch_seconds: float) -> str:
    return (
        datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _normalise_longitude(lon: float) -> float:
    normalised = (lon + 180.0) % 360.0 - 180.0
    return 180.0 if normalised == -180.0 and lon > 0 else normalised


def _displace(lat: float, lon: float, velocity: Vector, seconds: float) -> tuple[float, float]:
    """Move on a spherical Earth using a great-circle forward solution."""

    speed = velocity.speed
    if speed == 0.0 or seconds == 0.0:
        return lat, _normalise_longitude(lon)
    angular_distance = speed * seconds / EARTH_RADIUS_M
    bearing = math.atan2(velocity.east, velocity.north)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    sin_lat2 = (
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lat2 = math.asin(max(-1.0, min(1.0, sin_lat2)))
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), _normalise_longitude(math.degrees(lon2))


def _as_ascending(axis: Sequence[Any], label: str) -> tuple[list[float], bool]:
    values = [_finite(item, label) for item in axis]
    if not values:
        raise DriftInputError(f"{label} axis is empty")
    if len(values) == 1:
        return values, False
    increasing = all(left < right for left, right in pairwise(values))
    decreasing = all(left > right for left, right in pairwise(values))
    if not increasing and not decreasing:
        raise DriftInputError(f"{label} axis must be strictly monotonic")
    return (list(reversed(values)), True) if decreasing else (values, False)


def _normalise_cube(
    raw: Any,
    *,
    time_count: int,
    lat_count: int,
    lon_count: int,
    reverse_time: bool,
    reverse_lat: bool,
    reverse_lon: bool,
    label: str,
) -> list[list[list[float]]]:
    try:
        cube = [
            [[_finite(value, label) for value in row] for row in plane]
            for plane in raw
        ]
    except TypeError as exc:
        raise DriftInputError(f"{label} must be a [time][lat][lon] array") from exc
    if len(cube) != time_count:
        raise DriftInputError(f"{label} time dimension does not match its coordinate axis")
    if any(len(plane) != lat_count for plane in cube):
        raise DriftInputError(f"{label} latitude dimension does not match its coordinate axis")
    if any(len(row) != lon_count for plane in cube for row in plane):
        raise DriftInputError(f"{label} longitude dimension does not match its coordinate axis")
    if reverse_time:
        cube.reverse()
    if reverse_lat:
        cube = [list(reversed(plane)) for plane in cube]
    if reverse_lon:
        cube = [[list(reversed(row)) for row in plane] for plane in cube]
    return cube


def _bracket(axis: Sequence[float], value: float, label: str) -> tuple[int, int, float]:
    tolerance = max(1e-9, abs(axis[-1] - axis[0]) * 1e-12)
    if value < axis[0] - tolerance or value > axis[-1] + tolerance:
        raise DriftInputError(
            f"trajectory left the NetCDF {label} domain: {value:.6f} not in "
            f"[{axis[0]:.6f}, {axis[-1]:.6f}]"
        )
    value = min(axis[-1], max(axis[0], value))
    if len(axis) == 1:
        return 0, 0, 0.0
    upper = bisect.bisect_right(axis, value)
    if upper == 0:
        return 0, 0, 0.0
    if upper >= len(axis):
        last = len(axis) - 1
        return last, last, 0.0
    lower = upper - 1
    span = axis[upper] - axis[lower]
    return lower, upper, (value - axis[lower]) / span


def _lerp(left: float, right: float, ratio: float) -> float:
    return left + (right - left) * ratio


class RegularGridForcing:
    """Time-varying current/wind fields on a regular lat/lon CF grid."""

    def __init__(
        self,
        *,
        times: Sequence[Any],
        latitudes: Sequence[Any],
        longitudes: Sequence[Any],
        variables: Mapping[str, Any],
        source: str,
    ) -> None:
        epoch_times = []
        for item in times:
            if isinstance(item, datetime):
                utc_item = item.replace(tzinfo=timezone.utc) if item.tzinfo is None else item.astimezone(timezone.utc)
                epoch_times.append(utc_item.timestamp())
            else:
                epoch_times.append(_parse_time(item, "forcing time").timestamp())
        self.times, reverse_time = _as_ascending(epoch_times, "time")
        self.latitudes, reverse_lat = _as_ascending(latitudes, "latitude")
        self.longitudes, reverse_lon = _as_ascending(longitudes, "longitude")
        self.source = source

        supplied = set(variables)
        for component in REQUIRED_COMPONENTS:
            if component not in supplied:
                raise DriftInputError(f"forcing variable {component} is required")
        if ("wind_u" in supplied) != ("wind_v" in supplied):
            raise DriftInputError("wind_u and wind_v must be supplied together")
        if ("stokes_u" in supplied) != ("stokes_v" in supplied):
            raise DriftInputError("stokes_u and stokes_v must be supplied together")

        self.variables = {
            name: _normalise_cube(
                raw,
                time_count=len(self.times),
                lat_count=len(self.latitudes),
                lon_count=len(self.longitudes),
                reverse_time=reverse_time,
                reverse_lat=reverse_lat,
                reverse_lon=reverse_lon,
                label=name,
            )
            for name, raw in variables.items()
            if name in REQUIRED_COMPONENTS + WIND_COMPONENTS + OPTIONAL_COMPONENTS
        }

    @classmethod
    def from_inline(cls, config: Mapping[str, Any]) -> RegularGridForcing:
        coordinates = config.get("coordinates")
        variables = config.get("variables")
        if not isinstance(coordinates, Mapping) or not isinstance(variables, Mapping):
            raise DriftInputError("decoded-grid NetCDF input needs coordinates and variables")
        return cls(
            times=coordinates.get("time", []),
            latitudes=coordinates.get("latitude", []),
            longitudes=coordinates.get("longitude", []),
            variables=variables,
            source=str(config.get("source") or "local-decoded-netcdf-subset"),
        )

    @classmethod
    def from_netcdf(cls, config: Mapping[str, Any]) -> RegularGridForcing:
        """Load a local CF-NetCDF subset mounted in the Pyodide filesystem."""

        path = str(config.get("path") or "").strip()
        if not path:
            raise DriftInputError("netcdf.path is required for netcdf-cf input")
        if "://" in path:
            raise DriftInputError("netcdf.path must reference a local Pyodide filesystem file")
        local_path = Path(path)
        if not local_path.is_file():
            raise DriftInputError(f"local NetCDF subset does not exist: {path}")
        try:
            import netCDF4  # type: ignore
            import numpy as np  # type: ignore
        except ImportError as exc:
            raise DriftInputError(
                "netcdf-cf input requires Pyodide packages 'numpy' and 'netcdf4'"
            ) from exc

        requested_names = config.get("variables") or {}
        if not isinstance(requested_names, Mapping):
            raise DriftInputError("netcdf.variables must be an object")
        dimension_indices = config.get("dimension_indices") or {}
        if not isinstance(dimension_indices, Mapping):
            raise DriftInputError("netcdf.dimension_indices must be an object")

        def find_variable(dataset: Any, logical_name: str, candidates: Sequence[str], standards: Sequence[str]) -> str:
            explicit = requested_names.get(logical_name)
            if explicit:
                if str(explicit) not in dataset.variables:
                    raise DriftInputError(f"NetCDF variable {explicit!r} does not exist")
                return str(explicit)
            for name in candidates:
                if name in dataset.variables:
                    return name
            for name, variable in dataset.variables.items():
                if str(getattr(variable, "standard_name", "")).lower() in standards:
                    return name
            raise DriftInputError(f"could not identify NetCDF variable for {logical_name}")

        with netCDF4.Dataset(str(local_path), mode="r") as dataset:
            time_name = find_variable(dataset, "time", ("time",), ("time",))
            lat_name = find_variable(dataset, "latitude", ("latitude", "lat"), ("latitude",))
            lon_name = find_variable(dataset, "longitude", ("longitude", "lon"), ("longitude",))
            time_variable = dataset.variables[time_name]
            lat_variable = dataset.variables[lat_name]
            lon_variable = dataset.variables[lon_name]
            if len(time_variable.dimensions) != 1 or len(lat_variable.dimensions) != 1 or len(lon_variable.dimensions) != 1:
                raise DriftInputError("this kernel requires one-dimensional time/latitude/longitude coordinates")

            units = str(getattr(time_variable, "units", ""))
            if not units:
                raise DriftInputError("NetCDF time coordinate is missing CF units")
            calendar = str(getattr(time_variable, "calendar", "standard"))
            try:
                decoded_times = netCDF4.num2date(
                    time_variable[:],
                    units=units,
                    calendar=calendar,
                    only_use_cftime_datetimes=False,
                    only_use_python_datetimes=True,
                )
            except Exception as exc:
                raise DriftInputError("NetCDF time coordinate must use a standard UTC-compatible calendar") from exc

            time_dim = time_variable.dimensions[0]
            lat_dim = lat_variable.dimensions[0]
            lon_dim = lon_variable.dimensions[0]

            component_specs = {
                "current_u": (
                    ("uo", "water_u", "x_sea_water_velocity"),
                    ("eastward_sea_water_velocity",),
                    True,
                ),
                "current_v": (
                    ("vo", "water_v", "y_sea_water_velocity"),
                    ("northward_sea_water_velocity",),
                    True,
                ),
                "wind_u": (("u10", "wind_u", "x_wind"), ("eastward_wind",), False),
                "wind_v": (("v10", "wind_v", "y_wind"), ("northward_wind",), False),
                "stokes_u": (
                    ("ust", "stokes_u", "sea_surface_wave_stokes_drift_x_velocity"),
                    ("sea_surface_wave_stokes_drift_x_velocity",),
                    False,
                ),
                "stokes_v": (
                    ("vst", "stokes_v", "sea_surface_wave_stokes_drift_y_velocity"),
                    ("sea_surface_wave_stokes_drift_y_velocity",),
                    False,
                ),
            }

            arrays: dict[str, Any] = {}
            for logical_name, (candidates, standards, required) in component_specs.items():
                try:
                    variable_name = find_variable(dataset, logical_name, candidates, standards)
                except DriftInputError:
                    if required or requested_names.get(logical_name):
                        raise
                    continue
                variable = dataset.variables[variable_name]
                selection: list[Any] = []
                retained_dims: list[str] = []
                for dimension in variable.dimensions:
                    if dimension in {time_dim, lat_dim, lon_dim}:
                        selection.append(slice(None))
                        retained_dims.append(dimension)
                    else:
                        raw_index = dimension_indices.get(dimension, 0)
                        selection.append(_integer(raw_index, f"dimension index {dimension}", 0, len(dataset.dimensions[dimension]) - 1))
                data = np.ma.filled(variable[tuple(selection)], np.nan)
                if time_dim not in retained_dims:
                    data = np.expand_dims(data, axis=0)
                    retained_dims.insert(0, time_dim)
                missing_dims = {lat_dim, lon_dim} - set(retained_dims)
                if missing_dims:
                    raise DriftInputError(
                        f"NetCDF variable {variable_name!r} lacks dimensions {sorted(missing_dims)}"
                    )
                order = [retained_dims.index(time_dim), retained_dims.index(lat_dim), retained_dims.index(lon_dim)]
                data = np.transpose(data, axes=order)
                if data.shape[0] == 1 and len(decoded_times) > 1:
                    data = np.repeat(data, len(decoded_times), axis=0)
                if data.shape != (len(decoded_times), len(lat_variable), len(lon_variable)):
                    raise DriftInputError(
                        f"NetCDF variable {variable_name!r} does not align to [time, latitude, longitude]"
                    )
                data = data.astype(float) * _velocity_unit_scale(str(getattr(variable, "units", "m s-1")))
                arrays[logical_name] = data.tolist()

            return cls(
                times=list(decoded_times),
                latitudes=np.asarray(lat_variable[:], dtype=float).tolist(),
                longitudes=np.asarray(lon_variable[:], dtype=float).tolist(),
                variables=arrays,
                source=f"local-netcdf:{local_path.name}",
            )

    def _longitude_for_grid(self, lon: float) -> float:
        candidate = lon
        center = (self.longitudes[0] + self.longitudes[-1]) / 2.0
        while candidate - center > 180.0:
            candidate -= 360.0
        while candidate - center < -180.0:
            candidate += 360.0
        return candidate

    def sample(self, epoch_seconds: float, lat: float, lon: float) -> dict[str, float]:
        time0, time1, time_ratio = _bracket(self.times, epoch_seconds, "time")
        lat0, lat1, lat_ratio = _bracket(self.latitudes, lat, "latitude")
        grid_lon = self._longitude_for_grid(lon)
        lon0, lon1, lon_ratio = _bracket(self.longitudes, grid_lon, "longitude")

        def spatial(cube: list[list[list[float]]], time_index: int) -> float:
            south = _lerp(
                cube[time_index][lat0][lon0],
                cube[time_index][lat0][lon1],
                lon_ratio,
            )
            north = _lerp(
                cube[time_index][lat1][lon0],
                cube[time_index][lat1][lon1],
                lon_ratio,
            )
            return _lerp(south, north, lat_ratio)

        return {
            name: _lerp(spatial(cube, time0), spatial(cube, time1), time_ratio)
            for name, cube in self.variables.items()
        }


def _velocity_unit_scale(units: str) -> float:
    normalised = units.lower().strip().replace("**", "^").replace(" ", "")
    if normalised in {"", "m/s", "ms-1", "m.s-1", "metersecond-1", "metres-1"}:
        return 1.0
    if normalised in {"cm/s", "cms-1", "cm.s-1"}:
        return 0.01
    if normalised in {"km/h", "kmh-1", "km.h-1"}:
        return 1.0 / 3.6
    if normalised in {"knot", "knots", "kt", "kts"}:
        return 0.5144444444444445
    raise DriftInputError(f"unsupported NetCDF velocity unit {units!r}")


def _forcing_from_request(config: Any) -> RegularGridForcing:
    if not isinstance(config, Mapping):
        raise DriftInputError("netcdf must be an object")
    format_name = str(config.get("format") or "netcdf-cf").lower()
    if format_name == "decoded-grid/v1":
        return RegularGridForcing.from_inline(config)
    if format_name == "netcdf-cf":
        return RegularGridForcing.from_netcdf(config)
    raise DriftInputError("netcdf.format must be 'netcdf-cf' or 'decoded-grid/v1'")


def _leeway_velocity(wind: Vector, profile: LeewayProfile, side: str) -> Vector:
    wind_speed = wind.speed
    if wind_speed == 0.0:
        return Vector(0.0, 0.0)
    downwind_speed = max(
        0.0,
        (profile.downwind_slope * wind_speed + profile.downwind_offset) * 0.01,
    )
    if side == "right":
        crosswind_speed = (profile.right_slope * wind_speed + profile.right_offset) * 0.01
    elif side == "left":
        crosswind_speed = (profile.left_slope * wind_speed + profile.left_offset) * 0.01
    else:
        right = (profile.right_slope * wind_speed + profile.right_offset) * 0.01
        left = (profile.left_slope * wind_speed + profile.left_offset) * 0.01
        crosswind_speed = (right + left) / 2.0
    downwind_unit = Vector(wind.east / wind_speed, wind.north / wind_speed)
    clockwise_crosswind_unit = Vector(downwind_unit.north, -downwind_unit.east)
    return downwind_unit.scale(downwind_speed) + clockwise_crosswind_unit.scale(crosswind_speed)


@dataclass(frozen=True)
class SimulationConfig:
    start_lat: float
    start_lon: float
    start_time: datetime
    vessel_type: str
    model: str
    duration_seconds: int
    time_step_seconds: int
    output_interval_seconds: int
    leeway_side: str
    wind_drift_factor: float
    include_stokes: bool

    @classmethod
    def from_request(cls, request: Mapping[str, Any]) -> SimulationConfig:
        lkp = request.get("lkp")
        if not isinstance(lkp, Mapping):
            raise DriftInputError("lkp must be an object with lat and lon")
        lat = _finite(lkp.get("lat"), "lkp.lat")
        lon = _finite(lkp.get("lon"), "lkp.lon")
        if lat < -90.0 or lat > 90.0:
            raise DriftInputError("lkp.lat must be between -90 and 90")
        if lon < -180.0 or lon > 180.0:
            raise DriftInputError("lkp.lon must be between -180 and 180")
        vessel_type = str(request.get("vessel_type") or "unknown").strip().lower()
        if vessel_type not in LEEWAY_PROFILES:
            allowed = ", ".join(sorted(LEEWAY_PROFILES))
            raise DriftInputError(f"unsupported vessel_type {vessel_type!r}; expected one of {allowed}")
        model = str(request.get("model") or "leeway").strip().lower()
        if model not in {"leeway", "oceandrift"}:
            raise DriftInputError("model must be 'leeway' or 'oceandrift'")
        duration_seconds = _integer(
            request.get("duration_seconds", int(_finite(request.get("duration_hours", 24), "duration_hours") * 3600)),
            "duration_seconds",
            60,
            7 * 24 * 3600,
        )
        time_step = _integer(request.get("time_step_seconds", 900), "time_step_seconds", 10, 6 * 3600)
        output_interval = _integer(
            request.get("output_interval_seconds", 3600),
            "output_interval_seconds",
            time_step,
            24 * 3600,
        )
        if duration_seconds % time_step != 0:
            raise DriftInputError("duration_seconds must be a multiple of time_step_seconds")
        if output_interval % time_step != 0:
            raise DriftInputError("output_interval_seconds must be a multiple of time_step_seconds")
        side = str(request.get("leeway_side") or "mean").strip().lower()
        if side not in {"left", "right", "mean"}:
            raise DriftInputError("leeway_side must be 'left', 'right', or 'mean'")
        wind_drift_factor = _finite(request.get("wind_drift_factor", 0.0), "wind_drift_factor")
        if wind_drift_factor < 0.0 or wind_drift_factor > 0.2:
            raise DriftInputError("wind_drift_factor must be between 0 and 0.2")
        include_stokes = request.get("include_stokes", True)
        if not isinstance(include_stokes, bool):
            raise DriftInputError("include_stokes must be a JSON boolean")
        return cls(
            start_lat=lat,
            start_lon=lon,
            start_time=_parse_time(request.get("timestamp")),
            vessel_type=vessel_type,
            model=model,
            duration_seconds=duration_seconds,
            time_step_seconds=time_step,
            output_interval_seconds=output_interval,
            leeway_side=side,
            wind_drift_factor=wind_drift_factor,
            include_stokes=include_stokes,
        )


def _model_velocity(
    forcing: RegularGridForcing,
    config: SimulationConfig,
    epoch_seconds: float,
    lat: float,
    lon: float,
) -> Vector:
    values = forcing.sample(epoch_seconds, lat, lon)
    current = Vector(values["current_u"], values["current_v"])
    stokes = Vector(values.get("stokes_u", 0.0), values.get("stokes_v", 0.0))
    if not config.include_stokes:
        stokes = Vector(0.0, 0.0)
    wind = Vector(values.get("wind_u", 0.0), values.get("wind_v", 0.0))
    if config.model == "oceandrift":
        return current + wind.scale(config.wind_drift_factor) + stokes
    if "wind_u" not in values or "wind_v" not in values:
        raise DriftInputError("Leeway simulation requires wind_u and wind_v in the NetCDF subset")
    return current + _leeway_velocity(wind, LEEWAY_PROFILES[config.vessel_type], config.leeway_side) + stokes


def simulate(request: Mapping[str, Any]) -> dict[str, Any]:
    """Run a deterministic client-side trajectory and return GeoJSON only."""

    if not isinstance(request, Mapping):
        raise DriftInputError("simulation input must be a JSON object")
    config = SimulationConfig.from_request(request)
    forcing = _forcing_from_request(request.get("netcdf"))
    start_epoch = config.start_time.timestamp()
    end_epoch = start_epoch + config.duration_seconds
    _bracket(forcing.times, start_epoch, "time")
    _bracket(forcing.times, end_epoch, "time")

    lat = config.start_lat
    lon = config.start_lon
    coordinates: list[list[float]] = [[round(lon, 8), round(lat, 8)]]
    timestamps = [_iso_utc(start_epoch)]
    speed_ms = [0.0]
    output_every_steps = config.output_interval_seconds // config.time_step_seconds
    total_steps = config.duration_seconds // config.time_step_seconds

    for step in range(1, total_steps + 1):
        step_start = start_epoch + (step - 1) * config.time_step_seconds
        first_velocity = _model_velocity(forcing, config, step_start, lat, lon)
        mid_lat, mid_lon = _displace(
            lat,
            lon,
            first_velocity,
            config.time_step_seconds / 2.0,
        )
        midpoint = step_start + config.time_step_seconds / 2.0
        midpoint_velocity = _model_velocity(forcing, config, midpoint, mid_lat, mid_lon)
        lat, lon = _displace(lat, lon, midpoint_velocity, config.time_step_seconds)

        if step % output_every_steps == 0 or step == total_steps:
            coordinates.append([round(lon, 8), round(lat, 8)])
            timestamps.append(_iso_utc(step_start + config.time_step_seconds))
            speed_ms.append(round(midpoint_velocity.speed, 6))

    profile = LEEWAY_PROFILES[config.vessel_type]
    properties: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "engine": "seacommons-pyodide",
        "engine_version": ENGINE_VERSION,
        "model": config.model,
        "vessel_type": config.vessel_type,
        "forcing": forcing.source,
        "timestamps_utc": timestamps,
        "speed_ms": speed_ms,
        "operational_use": False,
    }
    if config.model == "leeway":
        properties["leeway_object_key"] = profile.object_key
        properties["leeway_side"] = config.leeway_side
    else:
        properties["wind_drift_factor"] = config.wind_drift_factor

    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": properties,
    }


def simulate_json(request_json: str) -> str:
    """Pyodide bridge: JSON input string -> JSON output string."""

    try:
        request = json.loads(request_json)
    except json.JSONDecodeError as exc:
        raise DriftInputError("input is not valid JSON") from exc
    result = simulate(request)
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def write_trajectory_json(request: Mapping[str, Any], output_path: str | Path) -> None:
    """Write exactly one UTF-8 JSON trajectory artefact."""

    path = Path(output_path)
    path.write_text(
        json.dumps(simulate(request), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Offline CLI helper: ``python seacommons_drift.py input.json output.json``."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 2:
        raise SystemExit("usage: seacommons_drift.py INPUT.json OUTPUT.json")
    request = json.loads(Path(arguments[0]).read_text(encoding="utf-8"))
    write_trajectory_json(request, arguments[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
