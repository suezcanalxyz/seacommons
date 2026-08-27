# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-process OpenDrift Leeway runner with lazy import and background pre-warm.

Why not subprocess?
  OpenDrift imports take ~50 s cold. Running as a subprocess restarts Python
  on every request, making the first drift compute take 50 s just for imports.
  This module imports OpenDrift once (in a background thread at API startup)
  and then reuses the live Leeway/reader_constant references for all requests.
  Each call creates its own Leeway instance so concurrent requests are safe.

Reader priority stack (highest wins):
  1. CMEMS NetCDF (reader_netCDF_CF_generic) — 0.083° resolution (~8 km),
       ocean currents from the Copernicus operational forecast model.
       Requires CMEMS_USERNAME + CMEMS_PASSWORD env vars.
  2. Open-Meteo _GridReader — 1.0° sample spacing, free, no credentials.
       5×5 grid with bilinear spatial + linear temporal interpolation.
       Falls back to this when CMEMS is unavailable.
  3. reader_constant — uniform forcing, produces straight trajectories.
       Last resort if both above fail.

  Layers 1 and 2 are additive: CMEMS provides ocean currents, Open-Meteo
  provides wind (even when CMEMS is active), so the simulation always has
  both forcing fields from the best available source.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import math
import os
import tempfile
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_ready = threading.Event()
_Leeway = None
_OceanDrift = None
_reader_constant = None
_reader_landmask = None
_grid_reader_cls = None  # lazily constructed after OpenDrift import

# Concurrency limiter — at most 1 OpenDrift simulation runs at a time.
# The 1 GB VM cannot handle concurrent CMEMS downloads + OpenDrift runs
# without exhausting memory and going into heavy swap (observed: 881 MB swap).
# A second call blocks here (in its background thread) until the slot is free.
_drift_semaphore = threading.Semaphore(1)
_drift_queue_count = 0  # approximate number of waiting sims (informational)

# Grid parameters for Open-Meteo spatially-varying reader.
# 5×5 at 1.0° spacing covers ±2° (≈220 km) around the start — large enough
# that a particle drifting at 2 m/s stays inside the grid for the full 24 h
# simulation. The old 3×3 / 0.5° grid (±0.5°, ≈55 km) caused straight
# trajectories because particles exited the grid in ~10 h and bilinear
# interpolation then clamped to constant edge values.
_GRID_N = 5          # 5×5 = 25 sample points
_GRID_DEG = 1.0      # spacing in degrees (≈111 km at equator, ≈95 km at 30°N)

# CMEMS NetCDF cache — files are kept for 3 h to avoid redundant downloads
_CMEMS_CACHE_DIR = Path(tempfile.gettempdir()) / "seacommons_cmems_cache"
_CMEMS_CACHE_TTL_S = 3 * 3600  # 3 hours


def _vector_components(
    speed_ms: float,
    direction_deg: float,
    *,
    direction_is_from: bool = False,
) -> tuple[float, float]:
    """Convert a north-referenced bearing to eastward/northward components."""
    factor = -1.0 if direction_is_from else 1.0
    radians = math.radians(direction_deg)
    return (
        factor * speed_ms * math.sin(radians),
        factor * speed_ms * math.cos(radians),
    )


def _surface_stokes_speed(hs_m: float, tp_s: float) -> float:
    """Deep-water surface Stokes drift speed from significant height and peak
    period (same bounded monochromatic estimate as the browser drift engine).

    Us = (2 * pi^3 / g) * Hs^2 / Tp^3, clamped to 0.35 m/s -- Hs and Tp are
    not a full directional spectrum, so this stays deliberately conservative.
    """
    if not (hs_m and tp_s) or hs_m <= 0 or tp_s <= 0:
        return 0.0
    us = (2.0 * math.pi**3 / 9.80665) * (hs_m**2) / (tp_s**3)
    return max(0.0, min(us, 0.35))


def _speed_to_ms(value: float, unit: str) -> float:
    normalized = unit.lower().strip()
    if normalized in {"km/h", "kmh", "kph"}:
        return value / 3.6
    if normalized in {"kn", "kt", "knots"}:
        return value * 0.514444
    if normalized in {"mph"}:
        return value * 0.44704
    return value


def _do_import() -> None:
    global _Leeway, _OceanDrift, _reader_constant, _reader_landmask
    with _lock:
        if _Leeway is not None:
            _ready.set()
            return
        logger.info("OpenDrift: importing models — this takes ~50 s on first load…")
        try:
            from opendrift.models.leeway import Leeway as _L
            from opendrift.models.oceandrift import OceanDrift as _OD
            from opendrift.readers import reader_constant as _rc
            _Leeway = _L
            _OceanDrift = _OD
            _reader_constant = _rc
            logger.info("OpenDrift: Leeway + OceanDrift import complete")
        except Exception as exc:
            logger.error("OpenDrift: import failed — %s", exc)
        try:
            from opendrift.readers import reader_global_landmask as _lm
            _reader_landmask = _lm
        except Exception as exc:  # optional — sim still runs without coastline
            logger.warning("OpenDrift: global landmask reader unavailable — %s", exc)
    _ready.set()


def _get_grid_reader_class():
    """Return the _GridReader class, building it once after OpenDrift is loaded."""
    global _grid_reader_cls
    if _grid_reader_cls is not None:
        return _grid_reader_cls

    import numpy as np
    rc = _reader_constant  # already loaded

    class _GridReader(rc.Reader):
        """
        Spatially and temporally varying reader built from an NxN Open-Meteo grid.

        At init time, a pre-fetched grid dict is provided.  On every call to
        get_variables(), OpenDrift passes the current (lon, lat) of the block
        being evaluated.  We bilinearly interpolate wind and ocean-current
        vectors to those positions, so particles that have drifted to different
        areas of the ocean experience different forcing — producing realistic
        curved trajectories.
        """

        def __init__(self, grid: dict, base_env: dict, start_time: datetime) -> None:
            super().__init__(base_env)
            self._grid = grid
            self._t0 = start_time
            if grid.get("has_waves"):
                for wave_var in (
                    "sea_surface_wave_stokes_drift_x_velocity",
                    "sea_surface_wave_stokes_drift_y_velocity",
                ):
                    if wave_var not in self.variables:
                        self.variables.append(wave_var)

        def get_variables(
            self, requested_variables, time=None, x=None, y=None,
            z=None, indrealization=None,
        ):
            # Fall back to reader_constant behaviour when coordinates are absent
            pmap = self._parameter_value_map
            base = {v: pmap[v] for v in requested_variables if v in pmap}
            if time is None or x is None:
                return base

            # reader_constant uses proj4='+proj=latlong', so x=lon, y=lat (degrees)
            lons_arr = np.atleast_1d(np.asarray(x, dtype=float)).ravel()
            lats_arr = np.atleast_1d(np.asarray(y, dtype=float)).ravel()

            elapsed_h = max(0.0, (time - self._t0).total_seconds() / 3600.0)
            t0_i = min(int(elapsed_h), self._grid["n_hours"] - 1)
            t1_i = min(t0_i + 1, self._grid["n_hours"] - 1)
            t_frac = elapsed_h - int(elapsed_h)

            gl = np.array(self._grid["lats"])  # ascending
            gn = np.array(self._grid["lons"])  # ascending

            # Grid cell indices for each particle position
            li = np.clip(np.searchsorted(gl, lats_arr) - 1, 0, len(gl) - 2)
            ni = np.clip(np.searchsorted(gn, lons_arr) - 1, 0, len(gn) - 2)

            dlat = np.where((gl[li + 1] - gl[li]) != 0, gl[li + 1] - gl[li], 1e-9)
            dlon = np.where((gn[ni + 1] - gn[ni]) != 0, gn[ni + 1] - gn[ni], 1e-9)
            lf = np.clip((lats_arr - gl[li]) / dlat, 0.0, 1.0)
            nf = np.clip((lons_arr - gn[ni]) / dlon, 0.0, 1.0)

            result = dict(base)

            for var, key in [
                ("x_wind", "wind_x"),
                ("y_wind", "wind_y"),
                ("x_sea_water_velocity", "u_current"),
                ("y_sea_water_velocity", "v_current"),
                ("sea_surface_wave_stokes_drift_x_velocity", "stokes_x"),
                ("sea_surface_wave_stokes_drift_y_velocity", "stokes_y"),
            ]:
                if var not in requested_variables or key not in self._grid:
                    continue
                arr = self._grid[key]  # shape (T, NLat, NLon)

                def bilin(t_i, _arr=arr):
                    v00 = _arr[t_i, li, ni]
                    v01 = _arr[t_i, li, ni + 1]
                    v10 = _arr[t_i, li + 1, ni]
                    v11 = _arr[t_i, li + 1, ni + 1]
                    return (
                        v00 * (1 - lf) * (1 - nf)
                        + v01 * (1 - lf) * nf
                        + v10 * lf * (1 - nf)
                        + v11 * lf * nf
                    )

                values = bilin(t0_i) * (1 - t_frac) + bilin(t1_i) * t_frac

                orig = np.asarray(x)
                result[var] = values.reshape(orig.shape) if orig.ndim > 1 else values

            return result

    _grid_reader_cls = _GridReader
    return _GridReader


def prewarm() -> None:
    """Start importing OpenDrift in a daemon thread. Call once at API startup."""
    t = threading.Thread(target=_do_import, daemon=True, name="opendrift-prewarm")
    t.start()
    logger.info("OpenDrift: pre-warm thread started")


def _fetch_grid(
    center_lat: float,
    center_lon: float,
    hours: int,
    start_time: datetime,
    fallback_wind_x: float = 0.0,
    fallback_wind_y: float = 0.0,
    fallback_u: float = 0.0,
    fallback_v: float = 0.0,
) -> dict[str, Any]:
    """
    Build a spatially-varying forcing grid by querying Open-Meteo atmosphere
    and Open-Meteo Marine APIs for a _GRID_N × _GRID_N set of points centred
    on (center_lat, center_lon).

    All HTTP calls are made in parallel (ThreadPoolExecutor).  Points that
    fail (land-masked, network error) are filled from the centre point.  If the
    centre itself fails (e.g. the whole region has no marine coverage), the
    fallback_* values from the weather API are used instead of zeros.

    Returns arrays covering every model hour including the final endpoint.
    """
    import numpy as np

    n = _GRID_N
    sp = _GRID_DEG
    offsets = [(k - n // 2) * sp for k in range(n)]
    lats = sorted([center_lat + dy for dy in offsets])
    lons = sorted([center_lon + dx for dx in offsets])
    sample_count = hours + 1
    utc_start = (
        start_time.replace(tzinfo=timezone.utc)
        if start_time.tzinfo is None
        else start_time.astimezone(timezone.utc)
    ).replace(minute=0, second=0, microsecond=0)
    utc_end = utc_start + timedelta(hours=hours)
    start_hour = utc_start.strftime("%Y-%m-%dT%H:%M")
    end_hour = utc_end.strftime("%Y-%m-%dT%H:%M")

    def fetch_point(lat: float, lon: float):
        wx = np.full(sample_count, np.nan)
        wy = np.full(sample_count, np.nan)
        uc = np.full(sample_count, np.nan)
        vc = np.full(sample_count, np.nan)
        sx = np.full(sample_count, np.nan)
        sy = np.full(sample_count, np.nan)

        # ── Atmospheric wind (Open-Meteo, always free) ────────────────────────
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat:.3f}&longitude={lon:.3f}"
                f"&hourly=wind_speed_10m,wind_direction_10m"
                f"&wind_speed_unit=ms&timezone=UTC"
                f"&start_hour={start_hour}&end_hour={end_hour}"
            )
            with urllib.request.urlopen(url, timeout=12) as r:
                d = json.loads(r.read())
            h = d.get("hourly", {})
            spds = h.get("wind_speed_10m", [])
            dirs = h.get("wind_direction_10m", [])
            for i in range(min(sample_count, len(spds))):
                ws = float(spds[i]) if spds[i] is not None else 5.0
                wd = float(dirs[i]) if dirs[i] is not None else 270.0
                wx[i], wy[i] = _vector_components(
                    ws,
                    wd,
                    direction_is_from=True,
                )
        except Exception as exc:
            logger.debug("Grid wind fetch %.2f,%.2f: %s", lat, lon, exc)

        # ── Ocean currents + waves (Open-Meteo Marine, free, no credentials) ──
        try:
            url = (
                f"https://marine-api.open-meteo.com/v1/marine"
                f"?latitude={lat:.3f}&longitude={lon:.3f}"
                f"&hourly=ocean_current_velocity,ocean_current_direction,"
                f"wave_height,wave_direction,wave_period"
                f"&timezone=UTC&cell_selection=sea"
                f"&start_hour={start_hour}&end_hour={end_hour}"
            )
            with urllib.request.urlopen(url, timeout=12) as r:
                d = json.loads(r.read())
            h = d.get("hourly", {})
            vels = h.get("ocean_current_velocity", [])
            dirs = h.get("ocean_current_direction", [])
            wave_h = h.get("wave_height", [])
            wave_d = h.get("wave_direction", [])
            wave_p = h.get("wave_period", [])
            velocity_unit = (
                d.get("hourly_units", {}).get("ocean_current_velocity")
                or "km/h"
            )
            for i in range(min(sample_count, len(vels))):
                raw_speed = float(vels[i]) if vels[i] is not None else 0.0
                cs = _speed_to_ms(raw_speed, velocity_unit)
                cd = float(dirs[i]) if dirs[i] is not None else 0.0
                uc[i], vc[i] = _vector_components(cs, cd)
            for i in range(min(sample_count, len(wave_h))):
                hs = float(wave_h[i]) if wave_h[i] is not None else 0.0
                tp = float(wave_p[i]) if i < len(wave_p) and wave_p[i] is not None else 0.0
                wd = float(wave_d[i]) if i < len(wave_d) and wave_d[i] is not None else 0.0
                us = _surface_stokes_speed(hs, tp)
                # Open-Meteo wave_direction is the direction waves come FROM.
                sx[i], sy[i] = _vector_components(us, wd, direction_is_from=True)
        except Exception as exc:
            logger.debug("Grid marine fetch %.2f,%.2f: %s", lat, lon, exc)

        return wx, wy, uc, vc, sx, sy

    wind_x = np.full((sample_count, n, n), np.nan)
    wind_y = np.full((sample_count, n, n), np.nan)
    u_curr = np.full((sample_count, n, n), np.nan)
    v_curr = np.full((sample_count, n, n), np.nan)
    stokes_x = np.full((sample_count, n, n), np.nan)
    stokes_y = np.full((sample_count, n, n), np.nan)

    point_map: dict[concurrent.futures.Future, tuple[int, int]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=n * n) as ex:
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                point_map[ex.submit(fetch_point, lat, lon)] = (i, j)
        for future in concurrent.futures.as_completed(point_map):
            i, j = point_map[future]
            try:
                wx, wy, uc_, vc_, sx_, sy_ = future.result()
                wind_x[:, i, j] = wx
                wind_y[:, i, j] = wy
                u_curr[:, i, j] = uc_
                v_curr[:, i, j] = vc_
                stokes_x[:, i, j] = sx_
                stokes_y[:, i, j] = sy_
            except Exception as exc:
                logger.debug("Grid point (%d,%d) failed: %s", i, j, exc)

    # Fill NaN cells (land-masked or failed) from the centre point.
    # If the centre itself is NaN (whole region has no marine data), use the
    # fallback values derived from the weather API rather than zero.
    ci = n // 2
    for arr, final_fallback in [
        (wind_x, fallback_wind_x),
        (wind_y, fallback_wind_y),
        (u_curr, fallback_u),
        (v_curr, fallback_v),
        # Waves: a missing value is genuinely no-wave-data, never a guess.
        (stokes_x, 0.0),
        (stokes_y, 0.0),
    ]:
        centre = arr[:, ci, ci].copy()
        for i in range(n):
            for j in range(n):
                mask = np.isnan(arr[:, i, j])
                if mask.any():
                    arr[mask, i, j] = centre[mask]
        arr[np.isnan(arr)] = final_fallback

    has_waves = bool(np.any(np.abs(stokes_x[:, ci, ci]) + np.abs(stokes_y[:, ci, ci]) > 1e-4))

    logger.info(
        "Grid fetch complete: %.2f,%.2f  wind_mean=(%.2f,%.2f) m/s  "
        "current_mean=(%.2f,%.2f) m/s",
        center_lat, center_lon,
        float(np.nanmean(wind_x[:, ci, ci])),
        float(np.nanmean(wind_y[:, ci, ci])),
        float(np.nanmean(u_curr[:, ci, ci])),
        float(np.nanmean(v_curr[:, ci, ci])),
    )

    return {
        "lats": lats,
        "lons": lons,
        "wind_x": wind_x,
        "wind_y": wind_y,
        "u_current": u_curr,
        "v_current": v_curr,
        "stokes_x": stokes_x,
        "stokes_y": stokes_y,
        "has_waves": has_waves,
        "n_hours": sample_count,
    }


def _build_cmems_reader(
    lat: float,
    lon: float,
    duration_h: int,
    start_time: datetime,
) -> Any | None:
    """
    Download a small CMEMS NetCDF slice (currents + wind) and return an
    OpenDrift reader_netCDF_CF_generic instance.

    Resolution: 0.083° ≈ 8 km.  Coverage: ±2° around the starting position,
    from start_time-1h to start_time+duration_h+1h.

    The slice is cached on disk for _CMEMS_CACHE_TTL_S seconds.  Concurrent
    calls for the same grid cell are serialised by a per-key lock so we never
    download the same file twice.

    Returns None (with a logged warning) if:
    - CMEMS credentials are not configured
    - copernicusmarine is not installed
    - the download times out or fails
    """
    from core.config import config as app_config  # imported lazily to avoid circular

    if not (app_config.CMEMS_USERNAME and app_config.CMEMS_PASSWORD):
        return None

    try:
        import copernicusmarine
        from opendrift.readers import reader_netCDF_CF_generic
    except ImportError as exc:
        logger.debug("CMEMS reader unavailable (missing package): %s", exc)
        return None

    # ── Cache key: rounded to 0.5° grid + hour bucket ─────────────────────────
    grid_lat = round(lat * 2) / 2      # 0.5° grid cell
    grid_lon = round(lon * 2) / 2
    hour_bucket = int(start_time.timestamp()) // _CMEMS_CACHE_TTL_S
    cache_key = f"cmems_{grid_lat:.1f}_{grid_lon:.1f}_{duration_h}h_{hour_bucket}"
    cache_key = cache_key.replace("-", "m").replace(".", "d")

    _CMEMS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    nc_path = _CMEMS_CACHE_DIR / f"{cache_key}.nc"

    # ── Per-key download lock ──────────────────────────────────────────────────
    # Prevents duplicate concurrent downloads for the same grid cell.
    if not hasattr(_build_cmems_reader, "_key_locks"):
        _build_cmems_reader._key_locks = {}  # type: ignore[attr-defined]
    key_lock = _build_cmems_reader._key_locks.setdefault(  # type: ignore[attr-defined]
        cache_key, threading.Lock()
    )

    with key_lock:
        # Check again after acquiring lock (another thread may have written it)
        if nc_path.exists() and (
            nc_path.stat().st_mtime + _CMEMS_CACHE_TTL_S > datetime.now(timezone.utc).timestamp()
        ):
            logger.info("CMEMS: using cached slice %s", nc_path.name)
        else:
            # ── Download ───────────────────────────────────────────────────────
            pad = 1.0  # ±1° gives ~240 km buffer — smaller file, faster download
            t_start = (start_time - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
            t_end = (start_time + timedelta(hours=duration_h + 1)).strftime("%Y-%m-%dT%H:%M:%S")

            def _normalize_lon(v: float) -> float:
                while v > 180:
                    v -= 360
                while v < -180:
                    v += 360
                return v

            norm_lon = _normalize_lon(lon)

            def _do_subset():
                copernicusmarine.subset(
                    dataset_id=app_config.CMEMS_CURRENT_DATASET,
                    username=app_config.CMEMS_USERNAME,
                    password=app_config.CMEMS_PASSWORD,
                    variables=["uo", "vo"],
                    minimum_longitude=norm_lon - pad,
                    maximum_longitude=norm_lon + pad,
                    minimum_latitude=lat - pad,
                    maximum_latitude=lat + pad,
                    # Dataset shallowest level is ~0.494 m; requesting 0.0
                    # triggers a harmless warning and gets clamped to 0.494.
                    minimum_depth=0.494,
                    maximum_depth=5.0,
                    start_datetime=t_start,
                    end_datetime=t_end,
                    output_filename=str(nc_path),
                    overwrite_output_data=True,
                )

            try:
                logger.info(
                    "CMEMS: downloading current slice %.2f,%.2f ±1° for %dh…",
                    lat, lon, duration_h,
                )
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
                    _fut = _ex.submit(_do_subset)
                    _fut.result(timeout=90)  # hard cap: fall back to Open-Meteo grid after 90s
                logger.info("CMEMS: download complete → %s (%.1f KB)",
                            nc_path.name, nc_path.stat().st_size / 1024)
            except concurrent.futures.TimeoutError:
                logger.warning("CMEMS download timed out after 90s — using Open-Meteo grid")
                nc_path.unlink(missing_ok=True)
                return None
            except Exception as exc:
                logger.warning("CMEMS download failed: %s", exc)
                nc_path.unlink(missing_ok=True)
                return None

    # ── Build OpenDrift reader from the NetCDF file ────────────────────────────
    try:
        reader = reader_netCDF_CF_generic.Reader(str(nc_path))
        logger.info(
            "CMEMS reader ready: covers %s → %s, variables=%s",
            reader.start_time, reader.end_time, reader.variables,
        )
        return reader
    except Exception as exc:
        logger.warning("CMEMS reader_netCDF_CF_generic failed: %s", exc)
        nc_path.unlink(missing_ok=True)
        return None


def _ensure_imported() -> None:
    """Block the calling thread until OpenDrift is imported."""
    if _Leeway is not None:
        return
    _do_import()
    if _Leeway is None:
        raise RuntimeError("OpenDrift is not installed or failed to import")


# ── GeoJSON helpers (copied from opendrift_runner, fixed to use timedelta) ───

def _representative_path(result_dataset: Any) -> tuple[list[list[float]], list[int]]:
    """Return a spherical ensemble centre for every valid output time."""
    lons = result_dataset.lon.values
    lats = result_dataset.lat.values
    n_traj, n_time = lons.shape
    coords: list[list[float]] = []
    time_indices: list[int] = []
    for t_index in range(n_time):
        col_lon = lons[:, t_index]
        col_lat = lats[:, t_index]
        pts = [
            (float(col_lon[i]), float(col_lat[i]))
            for i in range(n_traj)
            if not math.isnan(col_lon[i]) and not math.isnan(col_lat[i])
        ]
        if not pts:
            continue
        mean_x = sum(
            math.cos(math.radians(lat)) * math.cos(math.radians(lon))
            for lon, lat in pts
        ) / len(pts)
        mean_y = sum(
            math.cos(math.radians(lat)) * math.sin(math.radians(lon))
            for lon, lat in pts
        ) / len(pts)
        mean_z = sum(math.sin(math.radians(lat)) for _, lat in pts) / len(pts)
        mean_lon = math.degrees(math.atan2(mean_y, mean_x))
        mean_lat = math.degrees(math.atan2(mean_z, math.hypot(mean_x, mean_y)))
        coords.append([mean_lon, mean_lat])
        time_indices.append(t_index)
    return coords, time_indices


def _mean_path(result_dataset: Any) -> list[list[float]]:
    """Compatibility wrapper for callers that only need coordinates."""
    return _representative_path(result_dataset)[0]


def _haversine_m(first: list[float], second: list[float]) -> float:
    radius_m = 6_371_008.8
    lon1, lat1 = map(math.radians, first[:2])
    lon2, lat2 = map(math.radians, second[:2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * radius_m * math.asin(min(1.0, math.sqrt(value)))


def _bearing_deg(first: list[float], second: list[float]) -> float:
    lon1, lat1 = map(math.radians, first[:2])
    lon2, lat2 = map(math.radians, second[:2])
    dlon = lon2 - lon1
    east = math.sin(dlon) * math.cos(lat2)
    north = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    )
    return (math.degrees(math.atan2(east, north)) + 360) % 360


def _trajectory_properties(
    coords: list[list[float]],
    start_time: datetime,
    output_seconds: int,
    time_indices: list[int] | None = None,
) -> dict[str, Any]:
    """Build timestamps, drift speed and course from the modelled path."""
    indices = time_indices or list(range(len(coords)))
    timestamps = []
    for index in indices:
        sample_time = start_time + timedelta(seconds=index * output_seconds)
        sample_time = (
            sample_time.replace(tzinfo=timezone.utc)
            if sample_time.tzinfo is None
            else sample_time.astimezone(timezone.utc)
        )
        timestamps.append(sample_time.isoformat().replace("+00:00", "Z"))
    segment_distances = [
        _haversine_m(coords[index], coords[index + 1])
        for index in range(len(coords) - 1)
    ]
    segment_durations = [
        max(1, (indices[index + 1] - indices[index]) * output_seconds)
        for index in range(len(indices) - 1)
    ]
    segment_speeds = [
        distance / duration
        for distance, duration in zip(segment_distances, segment_durations)
    ]
    segment_courses = [
        _bearing_deg(coords[index], coords[index + 1])
        for index in range(len(coords) - 1)
    ]
    point_speeds = (
        [segment_speeds[0], *segment_speeds]
        if segment_speeds
        else [0.0] * len(coords)
    )
    point_courses = (
        [segment_courses[0], *segment_courses]
        if segment_courses
        else [0.0] * len(coords)
    )
    total_duration_s = sum(segment_durations)
    total_distance_m = sum(segment_distances)
    return {
        "type": "trajectory",
        "timestamps_utc": timestamps,
        "speed_ms": [round(value, 4) for value in point_speeds],
        "speed_kn": [round(value * 1.943844, 4) for value in point_speeds],
        "course_deg": [round(value, 2) for value in point_courses],
        "distance_m": round(total_distance_m, 1),
        "mean_speed_ms": round(
            total_distance_m / total_duration_s if total_duration_s else 0.0,
            4,
        ),
        "max_speed_ms": round(max(point_speeds, default=0.0), 4),
        "sample_interval_s": output_seconds,
        "sample_count": len(coords),
        "speed_basis": "geodesic displacement of OpenDrift ensemble centre",
    }


def _convex_hull(points: list[tuple[float, float]]) -> list[list[float]]:
    unique = sorted(set(points))
    if len(unique) <= 1:
        return [[p[0], p[1]] for p in unique]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return [[p[0], p[1]] for p in hull]


def _cloud_polygon(result_dataset: Any, time_index: int) -> dict[str, Any]:
    lons = result_dataset.lon.values
    lats = result_dataset.lat.values
    n_traj, n_time = lons.shape
    idx = max(0, min(time_index, n_time - 1))
    points: list[tuple[float, float]] = []
    for e in range(n_traj):
        lon = float(lons[e, idx])
        lat = float(lats[e, idx])
        if math.isnan(lon) or math.isnan(lat):
            continue
        points.append((lon, lat))
    if not points:
        return {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[]]},
            "properties": {"hours": 0},
        }
    if len(points) == 1:
        lon, lat = points[0]
        eps = 0.01
        hull = [
            [lon - eps, lat - eps], [lon + eps, lat - eps],
            [lon + eps, lat + eps], [lon - eps, lat + eps],
        ]
    else:
        hull = _convex_hull(points)
    if hull[0] != hull[-1]:
        hull.append(hull[0])
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [hull]},
        "properties": {"hours": idx},
    }


def _containment_polygon(result_dataset: Any, time_index: int) -> dict[str, Any]:
    """Probability-of-containment search area from the particle cloud.

    A convex hull of every particle is not a search area -- one stray or
    beached particle inflates it and it carries no probability. This fits a
    2-D Gaussian to the cloud (after trimming the farthest 10% for outlier
    resistance) and returns the 90%-containment ellipse, with the 50% ring
    in properties. Standard SAR drift practice.
    """
    import numpy as np

    lons = np.asarray(result_dataset.lon.values, dtype=float)
    lats = np.asarray(result_dataset.lat.values, dtype=float)
    n_traj, n_time = lons.shape
    idx = max(0, min(time_index, n_time - 1))
    lon_col = lons[:, idx]
    lat_col = lats[:, idx]
    valid = np.isfinite(lon_col) & np.isfinite(lat_col)
    plon = lon_col[valid]
    plat = lat_col[valid]

    if plon.size < 4:
        return _cloud_polygon(result_dataset, time_index)

    lat0 = float(np.median(plat))
    lon0 = float(np.median(plon))
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * max(0.1, math.cos(math.radians(lat0)))
    xs = (plon - lon0) * m_per_deg_lon
    ys = (plat - lat0) * m_per_deg_lat

    # Trim the farthest 10% (from the median centre) before fitting.
    dist = np.hypot(xs, ys)
    keep = dist <= np.quantile(dist, 0.90)
    if keep.sum() >= 4:
        xs, ys = xs[keep], ys[keep]

    cx, cy = float(np.mean(xs)), float(np.mean(ys))
    cov = np.cov(np.vstack([xs - cx, ys - cy]))
    if not np.all(np.isfinite(cov)):
        return _cloud_polygon(result_dataset, time_index)
    evals, evecs = np.linalg.eigh(cov)
    evals = np.clip(evals, 1.0, None)  # floor at 1 m^2 so a tight cloud still has an area

    # Mahalanobis^2 for 2 DOF: p=0.5 -> 1.3863, p=0.9 -> 4.6052
    k50, k90 = math.sqrt(1.3863), math.sqrt(4.6052)
    ax90 = np.sqrt(evals) * k90  # semi-axes in metres
    ax50 = np.sqrt(evals) * k50

    angle = math.atan2(evecs[1, 1], evecs[0, 1])
    ring: list[list[float]] = []
    for step in range(33):
        theta = 2 * math.pi * step / 32
        ex = ax90[1] * math.cos(theta)
        ey = ax90[0] * math.sin(theta)
        rx = ex * math.cos(angle) - ey * math.sin(angle)
        ry = ex * math.sin(angle) + ey * math.cos(angle)
        ring.append([
            lon0 + (cx + rx) / m_per_deg_lon,
            lat0 + (cy + ry) / m_per_deg_lat,
        ])

    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {
            "hours": idx,
            "method": "gaussian_containment",
            "particles": int(plon.size),
            "radius_p50_m": round(float(math.sqrt(ax50[0] * ax50[1])), 1),
            "radius_p90_m": round(float(math.sqrt(ax90[0] * ax90[1])), 1),
            "semi_axes_p90_m": [round(float(ax90[1]), 1), round(float(ax90[0]), 1)],
            "area_km2": round(float(math.pi * ax90[0] * ax90[1]) / 1e6, 2),
        },
    }


def _hours_to_index(hours: int, output_hours: list[int]) -> int:
    best_idx, best_diff = 0, 10 ** 9
    for idx, cur in enumerate(output_hours):
        d = abs(cur - hours)
        if d < best_diff:
            best_idx, best_diff = idx, d
    return best_idx


# ── Main entry point ──────────────────────────────────────────────────────────

def run_leeway(payload: dict[str, Any]) -> dict[str, Any]:
    """Run an OpenDrift Leeway simulation in the calling thread.

    Thread-safe: each call creates its own Leeway instance; module-level
    imports are read-only. At most _drift_semaphore.value simulations run
    concurrently — excess calls block until a slot is available.

    Raises RuntimeError on failure.
    """
    global _drift_queue_count
    _ensure_imported()

    _drift_queue_count += 1
    logger.info(
        "Drift queue: waiting for semaphore slot (pending=%d, lat=%.4f lon=%.4f)",
        _drift_queue_count,
        float(payload.get("lat", 0)),
        float(payload.get("lon", 0)),
    )
    _drift_semaphore.acquire()
    _drift_queue_count = max(0, _drift_queue_count - 1)
    try:
        logger.info("Drift semaphore acquired — starting simulation")
        return _run_leeway_inner(payload)
    finally:
        _drift_semaphore.release()
        logger.info("Drift semaphore released")


def _run_leeway_inner(payload: dict[str, Any]) -> dict[str, Any]:
    """Core simulation — called only when semaphore slot is held."""

    raw_time = payload["time_utc"]
    dt_val = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    if dt_val.tzinfo is not None:
        dt_val = dt_val.astimezone(timezone.utc).replace(tzinfo=None)
    start_time = dt_val

    duration_h = int(payload.get("duration_h", 24))
    env = payload.get("environment", {})
    particles = int(payload.get("particles", 32))
    time_step_s = int(payload.get("time_step_seconds", 900))
    output_s = int(payload.get("time_step_output_seconds", 3600))
    object_type = int(payload.get("object_type", 26))

    # Phase 15a: dispatch the OpenDrift model per object class. Leeway keeps
    # its SAR object_type coefficients; OceanDrift is used for powered/large
    # hulls (current-dominated, low windage) so a cargo ship is no longer
    # simulated with person-in-water leeway.
    model_name = str(payload.get("model", "leeway")).lower()
    object_class = str(payload.get("object_class", "") or "")
    wind_drift_factor = payload.get("wind_drift_factor")
    wind_drift_depth = payload.get("wind_drift_depth")
    if model_name == "oceandrift" and _OceanDrift is not None:
        sim = _OceanDrift(loglevel=50)
        sim.set_config("drift:stokes_drift", False)
        if wind_drift_depth is not None:
            try:
                sim.set_config("drift:wind_drift_depth", float(wind_drift_depth))
            except Exception:  # config key varies by OpenDrift version
                logger.debug("could not set drift:wind_drift_depth", exc_info=True)
    else:
        model_name = "leeway"
        sim = _Leeway(loglevel=50)
        sim.set_config("drift:stokes_drift", False)

    # Base constant env (used as fallback inside _GridReader). Zero Stokes is
    # the honest fallback for a position/time the wave grid does not cover.
    base_env = {
        "x_wind": float(env["x_wind"]),
        "y_wind": float(env["y_wind"]),
        "x_sea_water_velocity": float(env["x_sea_water_velocity"]),
        "y_sea_water_velocity": float(env["y_sea_water_velocity"]),
        "land_binary_mask": int(env.get("land_binary_mask", 0)),
        "sea_surface_wave_stokes_drift_x_velocity": 0.0,
        "sea_surface_wave_stokes_drift_y_velocity": 0.0,
    }

    # ── Reader priority stack ─────────────────────────────────────────────────
    #
    # OpenDrift appends each new reader to its per-variable priority list.
    # The 5x5 Open-Meteo grid supplies time-varying wind and fallback currents.
    # CMEMS is inserted with first=True below so its 0.083-degree currents take
    # precedence wherever its spatial/time domain covers the simulation.

    readers_added: list[str] = []
    grid_reader_added = False
    stokes_enabled = False
    landmask_added = False

    # _GridReader extends reader_constant.Reader and already inherits constant
    # fallback behaviour for every variable not covered by the grid (e.g.
    # land_binary_mask).  Adding a separate reader_constant instance alongside
    # it creates an ambiguous duplicate that can silently win the priority race
    # in OpenDrift and override the spatially-varying data with flat constants.
    #
    # Rule: add reader_constant ONLY when _GridReader is not available.

    # Layer 1 — Open-Meteo spatially-varying wind + currents (5×5 grid)
    try:
        grid = _fetch_grid(
            center_lat=float(payload["lat"]),
            center_lon=float(payload["lon"]),
            hours=duration_h,
            start_time=start_time,
            fallback_wind_x=base_env["x_wind"],
            fallback_wind_y=base_env["y_wind"],
            fallback_u=base_env["x_sea_water_velocity"],
            fallback_v=base_env["y_sea_water_velocity"],
        )
        GridReader = _get_grid_reader_class()
        sim.add_reader(GridReader(grid, base_env, start_time))
        readers_added.append("GridReader(Open-Meteo 5x5)")
        grid_reader_added = True
        # Phase 15b: enable wave-driven Stokes drift only when the marine
        # grid actually returned wave data. A missing wave field never
        # becomes a fabricated Stokes velocity.
        if grid.get("has_waves"):
            sim.set_config("drift:stokes_drift", True)
            stokes_enabled = True
            readers_added.append("Stokes(Open-Meteo waves)")
    except Exception as exc:
        logger.warning("Open-Meteo grid reader failed: %s", exc)

    # Layer 2 — CMEMS NetCDF (0.083°, requires credentials).
    # Added after GridReader so OpenDrift picks it up as the higher-priority
    # source for ocean current variables (last-added wins in OpenDrift ≥1.11).
    try:
        cmems_reader = _build_cmems_reader(
            lat=float(payload["lat"]),
            lon=float(payload["lon"]),
            duration_h=duration_h,
            start_time=start_time,
        )
        if cmems_reader is not None:
            # add_reader appends by default; first=True ensures CMEMS governs
            # ocean currents wherever its high-resolution domain is available.
            sim.add_reader(cmems_reader, first=True)
            readers_added.append("CMEMS-NetCDF(0.083°)")
    except Exception as exc:
        logger.warning("CMEMS reader failed: %s", exc)

    # Fallback — only when GridReader itself failed (e.g. Open-Meteo timeout).
    # _GridReader already provides constant behaviour through inheritance, so
    # this branch is only reached in degraded / offline conditions.
    if not grid_reader_added:
        sim.add_reader(_reader_constant.Reader(base_env))
        readers_added.append("reader_constant")

    # Phase 15b: real coastline so particles beach instead of drifting across
    # land. Added last so it governs land_binary_mask over the constant 0.
    if _reader_landmask is not None:
        try:
            sim.add_reader(_reader_landmask.Reader())
            readers_added.append("global_landmask")
            landmask_added = True
        except Exception as exc:
            logger.warning("landmask reader failed: %s", exc)

    logger.info("Drift readers active: %s", " → ".join(readers_added))
    seed_kwargs: dict[str, Any] = {
        "lon": float(payload["lon"]),
        "lat": float(payload["lat"]),
        "time": start_time,
        "radius": float(payload.get("seed_radius_m", 150)),
        "number": particles,
    }
    if model_name == "oceandrift":
        if wind_drift_factor is not None:
            seed_kwargs["wind_drift_factor"] = float(wind_drift_factor)
    else:
        seed_kwargs["object_type"] = object_type
    sim.seed_elements(**seed_kwargs)
    # Use timedelta objects — integer seconds trigger a conflict with internal
    # config state in OpenDrift 1.14.x, producing only 2 output time steps.
    sim.run(
        duration=timedelta(hours=duration_h),
        time_step=timedelta(seconds=time_step_s),
        time_step_output=timedelta(seconds=output_s),
    )

    result = sim.result
    coords, time_indices = _representative_path(result)
    if len(coords) < 2:
        raise RuntimeError("OpenDrift produced insufficient trajectory points")

    output_hours = [int(index * output_s / 3600) for index in time_indices]
    idx_6 = _hours_to_index(6, output_hours)
    idx_12 = _hours_to_index(12, output_hours)
    idx_24 = _hours_to_index(min(24, duration_h), output_hours)

    def _tagged_polygon(dataset, time_idx: int, cone_key: str) -> dict:
        feat = _containment_polygon(dataset, time_idx)
        props = dict(feat.get("properties") or {})
        props["type"] = cone_key
        return {**feat, "properties": props}

    trajectory_properties = _trajectory_properties(
        coords,
        start_time,
        output_s,
        time_indices,
    )
    forcing_resolution = (
        "0.083deg-CMEMS" if any("CMEMS" in reader for reader in readers_added)
        else "1.0deg-OpenMeteo-grid" if any("GridReader" in reader for reader in readers_added)
        else "constant"
    )
    forcing_quality = (
        "spatiotemporal"
        if forcing_resolution != "constant"
        else "degraded-constant"
    )

    return {
        "trajectory": {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": trajectory_properties,
        },
        "cone_6h": _tagged_polygon(result, idx_6, "cone_6h"),
        "cone_12h": _tagged_polygon(result, idx_12, "cone_12h"),
        "cone_24h": _tagged_polygon(result, idx_24, "cone_24h"),
        "impact_point": {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": coords[-1]},
                "properties": {"type": "impact_point", "hours": duration_h},
            }],
        },
        "metadata": {
            "domain": payload.get("domain", "ocean_sar"),
            "start_time": start_time.isoformat(),
            "duration_h": duration_h,
            "model": "OpenDrift OceanDrift" if model_name == "oceandrift" else "OpenDrift Leeway",
            "object_class": object_class or None,
            "operational_use": forcing_quality == "spatiotemporal",
            "stokes_drift": stokes_enabled,
            "landmask": "global_landmask" if landmask_added else None,
            "particles": particles,
            "object_type": object_type if model_name == "leeway" else None,
            "wind_drift_factor": float(wind_drift_factor) if (model_name == "oceandrift" and wind_drift_factor is not None) else None,
            "readers": readers_added,
            "forcing_resolution": forcing_resolution,
            "forcing_quality": forcing_quality,
            "trajectory_distance_m": trajectory_properties["distance_m"],
            "mean_drift_speed_ms": trajectory_properties["mean_speed_ms"],
            "max_drift_speed_ms": trajectory_properties["max_speed_ms"],
            "trajectory_samples": trajectory_properties["sample_count"],
            "time_step_seconds": time_step_s,
            "time_step_output_seconds": output_s,
            "forcing": {
                "x_wind": float(env["x_wind"]),
                "y_wind": float(env["y_wind"]),
                "x_sea_water_velocity": float(env["x_sea_water_velocity"]),
                "y_sea_water_velocity": float(env["y_sea_water_velocity"]),
            },
        },
    }
