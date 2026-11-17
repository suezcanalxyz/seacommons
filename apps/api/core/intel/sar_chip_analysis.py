"""Bounded experimental Sentinel-1 amplitude-chip analysis.

This is pixel analysis, NOT a vessel identification or geolocated detection.
Only small, already-cropped, local amplitude TIFFs are accepted. A scene's
STAC metadata alone cannot produce detections. The result must not enter the
corroborated maritime case graph until georeferencing and independent review.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

MAX_CHIP_PIXELS = 1024 * 1024
MAX_TIFF_BYTES = 64 * 1024 * 1024


def analyze_amplitude_chip(
    amplitude: np.ndarray,
    *,
    scene_id: str = "unassigned",
    guard_size: int = 5,
    window_size: int = 21,
    threshold_sigma: float = 6.0,
    min_area_px: int = 3,
) -> dict[str, Any]:
    """Guard-ring CFAR bright-scatterer candidates in a bounded SAR chip.

    Input must be linear amplitude, not an RGB preview, optical image or dB
    rendering. Returns pixel locations only, never inferred vessel positions.
    """
    chip = np.asarray(amplitude)
    if chip.ndim != 2 or not (32 <= chip.shape[0] and 32 <= chip.shape[1]):
        raise ValueError("expected a 2D SAR amplitude chip of at least 32x32")
    if chip.size > MAX_CHIP_PIXELS:
        raise ValueError("chip exceeds bounded pixel-analysis budget")
    if not np.issubdtype(chip.dtype, np.number) or np.iscomplexobj(chip):
        raise ValueError("chip must contain real numeric SAR amplitudes")
    if not (3 <= guard_size < window_size and guard_size % 2 and window_size % 2):
        raise ValueError("guard and background windows must be odd and ordered")
    if threshold_sigma < 3 or min_area_px < 1:
        raise ValueError("invalid detection thresholds")

    values = chip.astype(np.float32, copy=False)
    valid = np.isfinite(values) & (values >= 0)
    if valid.mean() < 0.99:
        raise ValueError("chip has insufficient finite nonnegative amplitude pixels")
    power = np.square(np.where(valid, values, 0.0))
    outer_n = window_size * window_size
    guard_n = guard_size * guard_size
    outer_mean = ndimage.uniform_filter(power, size=window_size, mode="reflect")
    guard_mean = ndimage.uniform_filter(power, size=guard_size, mode="reflect")
    background = np.maximum(0.0, (outer_mean * outer_n - guard_mean * guard_n) / (outer_n - guard_n))
    squared = np.square(power)
    outer_sq = ndimage.uniform_filter(squared, size=window_size, mode="reflect")
    guard_sq = ndimage.uniform_filter(squared, size=guard_size, mode="reflect")
    background_sq = np.maximum(0.0, (outer_sq * outer_n - guard_sq * guard_n) / (outer_n - guard_n))
    deviation = np.sqrt(np.maximum(0.0, background_sq - np.square(background)))
    candidates = valid & (power > background + threshold_sigma * deviation) & (power > 5 * background)
    labels, count = ndimage.label(candidates)
    boxes = ndimage.find_objects(labels)
    targets: list[dict[str, Any]] = []
    for label_id in range(1, count + 1):
        bounds = boxes[label_id - 1]
        if bounds is None:
            continue
        component = labels[bounds] == label_id
        area = int(component.sum())
        if area < min_area_px:
            continue
        rows, cols = np.nonzero(component)
        r0, c0 = bounds[0].start, bounds[1].start
        target_power = float(np.median(power[bounds][component]))
        sea_power = float(np.median(background[bounds][component]))
        targets.append({
            "row": round(float(rows.mean() + r0), 2),
            "col": round(float(cols.mean() + c0), 2),
            "bbox_px": [c0, r0, bounds[1].stop, bounds[0].stop],
            "area_px": area,
            "contrast_db": round(float(10 * np.log10(max(target_power, 1e-8) / max(sea_power, 1e-8))), 2),
            "classification": "unverified_bright_scatterer",
        })
        if len(targets) >= 100:
            break
    return {
        "scene_id": scene_id,
        "analysis_method": "guard_ring_cfar_linear_amplitude",
        "analysis_level": "pixel_chip_unverified",
        "shape_px": list(chip.shape),
        "georeferenced": False,
        "confirmed_vessel": False,
        "candidate_bright_scatterers": targets,
    }


def analyze_local_tiff_chip(path: str | Path, *, scene_id: str = "unassigned") -> dict[str, Any]:
    """Read a bounded local TIFF chip. Full Sentinel-1 GRD scenes are refused."""
    from tifffile import TiffFile

    source = Path(path)
    if source.stat().st_size > MAX_TIFF_BYTES:
        raise ValueError("TIFF exceeds bounded input budget")
    with TiffFile(source) as tif:
        if len(tif.pages) != 1 or len(tif.pages[0].shape) != 2:
            raise ValueError("expected one single-band SAR amplitude TIFF page")
        if np.prod(tif.pages[0].shape) > MAX_CHIP_PIXELS:
            raise ValueError("TIFF exceeds bounded pixel-analysis budget")
        chip = tif.pages[0].asarray()
    return analyze_amplitude_chip(chip, scene_id=scene_id)
