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
       real ocean currents from Copernicus operational forecast.
       Requires CMEMS_USERNAME + CMEMS_PASSWORD env vars.
       Covers wind from ERA5 (via CMEMS wave dataset) and currents from
       the global physics analysis/forecast model.
  2. Open-Meteo _GridReader — 0.5° resolution (~55 km), free, no credentials.
       3×3 grid with bilinear spatial + linear temporal interpolation.
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
_reader_constant = None
_grid_reader_cls = None  # lazily constructed after OpenDrift import

# Concurrency limiter — at most 1 OpenDrift simulation runs at a time.
# The 1 GB VM cannot handle concurrent CMEMS downloads + OpenDrift runs
# without exhausting memory and going into heavy swap (observed: 881 MB swap).
# A second call blocks here (in its background thread) until the slot is free.
_drift_semaphore = threading.Semaphore(1)
_drift_queue_count = 0  # approximate number of waiting sims (informational)

# Grid parameters for Open-Meteo spatially-varying reader
_GRID_N = 3          # 3×3 = 9 sample points
_GRID_DEG = 0.5      # spacing in degrees (≈55 km at Mediterranean latitudes)

# CMEMS NetCDF cache — files are kept for 3 h to avoid redundant downloads
_CMEMS_CACHE_DIR = Path(tempfile.gettempdir()) / "seacommons_cmems_cache"
_CMEMS_CACHE_TTL_S = 3 * 3600  # 3 hours


def _do_import() -> None:
    global _Leeway, _reader_constant
    with _lock:
        if _Leeway is not None:
            _ready.set()
            return
        logger.info("OpenDrift: importing Leeway — this takes ~50 s on first load…")
        try:
            from opendrift.models.leeway import Leeway as _L
            from opendrift.readers import reader_constant as _rc
            _Leeway = _L
            _reader_constant = _rc
            logger.info("OpenDrift: Leeway import complete")
        except Exception as exc:
            logger.error("OpenDrift: import failed — %s", exc)
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

        def get_variables(
            self, requested_variables, time=None, x=None, y=None,
            z=None, indrealization=None,
        ):
            # Fall back to reader_constant behaviour when coordinates are absent
            base = {v: self.data[v] for v in requested_variables if v in self.data}
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


def _fetch_grid(center_lat: float, center_lon: float, hours: int) -> dict[str, Any]:
    """
    Build a spatially-varying forcing grid by querying Open-Meteo atmosphere
    and Open-Meteo Marine APIs for a _GRID_N × _GRID_N set of points centred
    on (center_lat, center_lon).

    All HTTP calls are made in parallel (ThreadPoolExecutor).  Points that
    fail (land-masked, network error) are filled from the centre point so the
    simulation always gets valid data.

    Returns a dict with numpy arrays of shape (hours, GRID_N, GRID_N).
    """
    import numpy as np

    n = _GRID_N
    sp = _GRID_DEG
    offsets = [(k - n // 2) * sp for k in range(n)]
    lats = sorted([center_lat + dy for dy in offsets])
    lons = sorted([center_lon + dx for dx in offsets])
    forecast_days = max(2, hours // 24 + 1)

    def fetch_point(lat: float, lon: float):
        wx = np.full(hours, np.nan)
        wy = np.full(hours, np.nan)
        uc = np.full(hours, np.nan)
        vc = np.full(hours, np.nan)

        # ── Atmospheric wind (Open-Meteo, always free) ────────────────────────
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat:.3f}&longitude={lon:.3f}"
                f"&hourly=wind_speed_10m,wind_direction_10m"
                f"&wind_speed_unit=ms&forecast_days={forecast_days}"
            )
            with urllib.request.urlopen(url, timeout=12) as r:
                d = json.loads(r.read())
            h = d.get("hourly", {})
            spds = h.get("wind_speed_10m", [])
            dirs = h.get("wind_direction_10m", [])
            for i in range(min(hours, len(spds))):
                ws = float(spds[i]) if spds[i] is not None else 5.0
                wd = float(dirs[i]) if dirs[i] is not None else 270.0
                rad = math.radians(wd)
                wx[i] = ws * math.sin(rad)
                wy[i] = ws * math.cos(rad)
        except Exception as exc:
            logger.debug("Grid wind fetch %.2f,%.2f: %s", lat, lon, exc)

        # ── Ocean currents (Open-Meteo Marine, free, global, no credentials) ──
        try:
            url = (
                f"https://marine-api.open-meteo.com/v1/marine"
                f"?latitude={lat:.3f}&longitude={lon:.3f}"
                f"&hourly=ocean_current_velocity,ocean_current_direction"
                f"&forecast_days={forecast_days}"
            )
            with urllib.request.urlopen(url, timeout=12) as r:
                d = json.loads(r.read())
            h = d.get("hourly", {})
            vels = h.get("ocean_current_velocity", [])
            dirs = h.get("ocean_current_direction", [])
            for i in range(min(hours, len(vels))):
                cs = float(vels[i]) if vels[i] is not None else 0.0
                cd = float(dirs[i]) if dirs[i] is not None else 0.0
                crad = math.radians(cd)
                uc[i] = cs * math.sin(crad)
                vc[i] = cs * math.cos(crad)
        except Exception as exc:
            logger.debug("Grid marine fetch %.2f,%.2f: %s", lat, lon, exc)

        return wx, wy, uc, vc

    wind_x = np.full((hours, n, n), np.nan)
    wind_y = np.full((hours, n, n), np.nan)
    u_curr = np.full((hours, n, n), np.nan)
    v_curr = np.full((hours, n, n), np.nan)

    point_map: dict[concurrent.futures.Future, tuple[int, int]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=n * n) as ex:
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                point_map[ex.submit(fetch_point, lat, lon)] = (i, j)
        for future in concurrent.futures.as_completed(point_map):
            i, j = point_map[future]
            try:
                wx, wy, uc_, vc_ = future.result()
                wind_x[:, i, j] = wx
                wind_y[:, i, j] = wy
                u_curr[:, i, j] = uc_
                v_curr[:, i, j] = vc_
            except Exception as exc:
                logger.debug("Grid point (%d,%d) failed: %s", i, j, exc)

    # Fill NaN cells (land-masked or failed) from the centre point
    ci = n // 2
    for arr in (wind_x, wind_y, u_curr, v_curr):
        centre = arr[:, ci, ci].copy()
        for i in range(n):
            for j in range(n):
                mask = np.isnan(arr[:, i, j])
                if mask.any():
                    arr[mask, i, j] = centre[mask]
        # If centre itself is NaN (shouldn't happen but defensive), fill zeros
        arr[np.isnan(arr)] = 0.0

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
        "n_hours": hours,
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
                    minimum_depth=0.0,
                    maximum_depth=5.0,
                    start_datetime=t_start,
                    end_datetime=t_end,
                    output_filename=str(nc_path),
                    force_download=True,
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

def _mean_path(result_dataset: Any) -> list[list[float]]:
    lons = result_dataset.lon.values
    lats = result_dataset.lat.values
    n_traj, n_time = lons.shape
    coords: list[list[float]] = []
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
        coords.append([
            sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts),
        ])
    return coords


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

    sim = _Leeway(loglevel=50)
    sim.set_config("drift:stokes_drift", False)

    # Base constant env (used as fallback inside _GridReader and as the
    # land_binary_mask source which the grid doesn't provide)
    base_env = {
        "x_wind": float(env["x_wind"]),
        "y_wind": float(env["y_wind"]),
        "x_sea_water_velocity": float(env["x_sea_water_velocity"]),
        "y_sea_water_velocity": float(env["y_sea_water_velocity"]),
        "land_binary_mask": int(env.get("land_binary_mask", 0)),
    }

    # ── Reader priority stack ─────────────────────────────────────────────────
    #
    # OpenDrift merges multiple readers: each reader covers a subset of
    # variables and a spatial domain.  We add them highest-priority last
    # (OpenDrift reads from the last-added reader that covers the variable).
    # Actually OpenDrift's convention is first-added = highest priority, so
    # we add in descending priority order.
    #
    # Priority 1 (highest): reader_constant — always added first as the
    #   universal fallback for variables not covered by higher-priority readers.
    #
    # Priority 2: Open-Meteo _GridReader — replaces wind + currents with
    #   spatially and temporally varying values from a 3×3 free grid.
    #
    # Priority 3 (highest): CMEMS reader_netCDF_CF_generic — when credentials
    #   are configured, replaces ocean currents with 0.083° Copernicus data.
    #   Wind comes from _GridReader (Open-Meteo) since CMEMS current-only
    #   datasets don't include wind components.
    #
    # OpenDrift resolves variable-level conflicts: if CMEMS covers uo/vo but
    # not x_wind/y_wind, the _GridReader fills the wind gap automatically.

    readers_added: list[str] = []

    # Layer 1 — universal fallback (lowest priority)
    sim.add_reader(_reader_constant.Reader(base_env))
    readers_added.append("reader_constant")

    # Layer 2 — Open-Meteo spatially-varying wind + currents
    try:
        grid = _fetch_grid(
            center_lat=float(payload["lat"]),
            center_lon=float(payload["lon"]),
            hours=duration_h,
        )
        GridReader = _get_grid_reader_class()
        sim.add_reader(GridReader(grid, base_env, start_time))
        readers_added.append("GridReader(Open-Meteo 3×3)")
    except Exception as exc:
        logger.warning("Open-Meteo grid reader failed: %s", exc)

    # Layer 3 — CMEMS NetCDF (0.083°, requires credentials)
    try:
        cmems_reader = _build_cmems_reader(
            lat=float(payload["lat"]),
            lon=float(payload["lon"]),
            duration_h=duration_h,
            start_time=start_time,
        )
        if cmems_reader is not None:
            sim.add_reader(cmems_reader)
            readers_added.append("CMEMS-NetCDF(0.083°)")
    except Exception as exc:
        logger.warning("CMEMS reader failed: %s", exc)

    logger.info("Drift readers active: %s", " → ".join(readers_added))
    sim.seed_elements(
        lon=float(payload["lon"]),
        lat=float(payload["lat"]),
        time=start_time,
        radius=float(payload.get("seed_radius_m", 150)),
        number=particles,
        object_type=object_type,
    )
    # Use timedelta objects — integer seconds trigger a conflict with internal
    # config state in OpenDrift 1.14.x, producing only 2 output time steps.
    sim.run(
        duration=timedelta(hours=duration_h),
        time_step=timedelta(seconds=time_step_s),
        time_step_output=timedelta(seconds=output_s),
    )

    result = sim.result
    coords = _mean_path(result)
    if len(coords) < 2:
        raise RuntimeError("OpenDrift produced insufficient trajectory points")

    output_hours = [int(i * output_s / 3600) for i in range(len(coords))]
    idx_6 = _hours_to_index(6, output_hours)
    idx_12 = _hours_to_index(12, output_hours)
    idx_24 = _hours_to_index(min(24, duration_h), output_hours)

    def _tagged_polygon(dataset, time_idx: int, cone_key: str) -> dict:
        feat = _cloud_polygon(dataset, time_idx)
        props = dict(feat.get("properties") or {})
        props["type"] = cone_key
        return {**feat, "properties": props}

    return {
        "trajectory": {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"type": "trajectory"},
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
            "model": "OpenDrift Leeway",
            "particles": particles,
            "object_type": object_type,
            "readers": readers_added,
            "forcing_resolution": (
                "0.083deg-CMEMS" if any("CMEMS" in r for r in readers_added)
                else "0.5deg-OpenMeteo" if any("GridReader" in r for r in readers_added)
                else "constant"
            ),
            "forcing": {
                "x_wind": float(env["x_wind"]),
                "y_wind": float(env["y_wind"]),
                "x_sea_water_velocity": float(env["x_sea_water_velocity"]),
                "y_sea_water_velocity": float(env["y_sea_water_velocity"]),
            },
        },
    }
