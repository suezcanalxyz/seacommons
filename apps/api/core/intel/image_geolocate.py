# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recover a map-pin's real-world position from labelled landmarks (docs/prompt.md §7).

`map_pin_geolocate` fitted `pixel = slope·latitude + intercept` and
`pixel = slope·longitude + intercept` independently. Every slippy map is Web
Mercator: the pixels-per-degree of latitude grows with latitude, so a linear
fit in *degrees* is biased, and the bias grows toward the frame edges and
with extrapolation distance -- exactly the "boat 200 km south of Crete" case
this feature exists for.

This module fits the transform in Mercator space instead:

    landmark WGS84  ->  Web Mercator (x, y)
    robust affine pixel<->mercator fit (RANSAC when >= 4 labels)
    pin pixel  ->  inverse fit  ->  Mercator  ->  WGS84

and returns the fit residual, the extrapolation distance and a propagated
position-error estimate so the caller can size the uncertainty honestly and
refuse a poor fit rather than publish a confident wrong point.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

_EARTH_RADIUS_M = 6_378_137.0
_LAT_RANGE = (20.0, 48.0)
_LON_RANGE = (-12.0, 42.0)
_MIN_LANDMARKS = 2
_MIN_PIXEL_SPREAD = 20.0
# A genuinely wrong label match (OCR misread / wrong instance of an ambiguous
# name) rather than normal far-offshore extrapolation.
_RANSAC_INLIER_PX = 24.0


def _merc(lat: float, lon: float) -> tuple[float, float]:
    lat = max(-85.05, min(85.05, lat))
    x = math.radians(lon) * _EARTH_RADIUS_M
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * _EARTH_RADIUS_M
    return x, y


def _inv_merc(x: float, y: float) -> tuple[float, float]:
    lon = math.degrees(x / _EARTH_RADIUS_M)
    lat = math.degrees(2 * math.atan(math.exp(y / _EARTH_RADIUS_M)) - math.pi / 2)
    return lat, lon


@dataclass
class Landmark:
    name: str
    px: float
    py: float
    lat: float
    lon: float


@dataclass
class GeolocationSolution:
    lat: float
    lon: float
    landmarks_used: list[str]
    landmarks_detected: list[str]
    fit_residual_px: float
    max_extrapolation_px: float
    estimated_position_error_m: float
    confidence: float
    method: str = "web_mercator_affine"
    notes: list[str] = field(default_factory=list)


def _fit_axis(independent: list[float], dependent: list[float]) -> Optional[tuple[float, float]]:
    """Least-squares dependent = slope*independent + intercept."""
    n = len(independent)
    if n < 2 or max(independent) - min(independent) < 1e-6:
        return None
    mean_x = sum(independent) / n
    mean_y = sum(dependent) / n
    sxx = sum((x - mean_x) ** 2 for x in independent)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(independent, dependent))
    if sxx < 1e-9:
        return None
    slope = sxy / sxx
    return slope, mean_y - slope * mean_x


def _residual_px(landmarks: list[Landmark], fx: tuple[float, float], fy: tuple[float, float]) -> float:
    total = 0.0
    for lm in landmarks:
        mx, my = _merc(lm.lat, lm.lon)
        predicted_px = fx[0] * mx + fx[1]
        predicted_py = fy[0] * my + fy[1]
        total += math.hypot(predicted_px - lm.px, predicted_py - lm.py)
    return total / len(landmarks)


def _fit(landmarks: list[Landmark]) -> Optional[tuple[tuple[float, float], tuple[float, float]]]:
    merc = [_merc(lm.lat, lm.lon) for lm in landmarks]
    fx = _fit_axis([m[0] for m in merc], [lm.px for lm in landmarks])
    fy = _fit_axis([m[1] for m in merc], [lm.py for lm in landmarks])
    if fx is None or fy is None or abs(fx[0]) < 1e-12 or abs(fy[0]) < 1e-12:
        return None
    return fx, fy


def _ransac(landmarks: list[Landmark]) -> tuple[list[Landmark], list[str]]:
    """Drop outlier label matches. Tries every pair as a minimal model, keeps
    the largest inlier set, refits on it."""
    best_inliers: list[Landmark] = []
    for i in range(len(landmarks)):
        for j in range(i + 1, len(landmarks)):
            model = _fit([landmarks[i], landmarks[j]])
            if model is None:
                continue
            fx, fy = model
            inliers = []
            for lm in landmarks:
                mx, my = _merc(lm.lat, lm.lon)
                err = math.hypot(fx[0] * mx + fx[1] - lm.px, fy[0] * my + fy[1] - lm.py)
                if err <= _RANSAC_INLIER_PX:
                    inliers.append(lm)
            if len(inliers) > len(best_inliers):
                best_inliers = inliers
    if len(best_inliers) >= 3:
        dropped = [lm.name for lm in landmarks if lm not in best_inliers]
        return best_inliers, dropped
    return landmarks, []


def solve_pin_position(
    pin_px: tuple[float, float],
    landmarks: list[Landmark],
    *,
    image_size: tuple[int, int],
) -> Optional[GeolocationSolution]:
    """Best-effort pin position from >= 2 labelled landmarks, or None."""
    detected = [lm.name for lm in landmarks]
    if len(landmarks) < _MIN_LANDMARKS:
        return None

    notes: list[str] = []
    used = list(landmarks)
    if len(landmarks) >= 4:
        used, dropped = _ransac(landmarks)
        if dropped:
            notes.append(f"dropped outlier label(s): {', '.join(dropped)}")

    px_spread = max(lm.px for lm in used) - min(lm.px for lm in used)
    py_spread = max(lm.py for lm in used) - min(lm.py for lm in used)
    if px_spread < _MIN_PIXEL_SPREAD or py_spread < _MIN_PIXEL_SPREAD:
        return None

    model = _fit(used)
    if model is None:
        return None
    fx, fy = model

    residual = _residual_px(used, fx, fy)
    pin_x, pin_y = pin_px
    mx = (pin_x - fx[1]) / fx[0]
    my = (pin_y - fy[1]) / fy[0]
    lat, lon = _inv_merc(mx, my)
    if not (_LAT_RANGE[0] <= lat <= _LAT_RANGE[1] and _LON_RANGE[0] <= lon <= _LON_RANGE[1]):
        return None

    # Extrapolation: how far outside the labelled pixel hull the pin sits.
    left, right = min(lm.px for lm in used), max(lm.px for lm in used)
    top, bottom = min(lm.py for lm in used), max(lm.py for lm in used)
    extrapolation_px = max(
        0.0, left - pin_x, pin_x - right, top - pin_y, pin_y - bottom
    )

    # Propagate: metres-per-pixel at the pin latitude, times (residual +
    # a fraction of the extrapolation distance).
    m_per_px_x = abs(1.0 / fx[0])
    m_per_px_y = abs(1.0 / fy[0]) / math.cos(math.radians(lat))
    m_per_px = (m_per_px_x + m_per_px_y) / 2
    error_m = m_per_px * (residual + 0.5 * extrapolation_px) + 150.0

    diagonal_px = math.hypot(*image_size) or 1.0
    confidence = max(
        0.05,
        min(
            0.7,
            (0.75 if len(used) >= 3 else 0.35)
            - residual / 60.0
            - extrapolation_px / (2 * diagonal_px),
        ),
    )
    return GeolocationSolution(
        lat=round(lat, 5),
        lon=round(lon, 5),
        landmarks_used=[lm.name for lm in used],
        landmarks_detected=detected,
        fit_residual_px=round(residual, 1),
        max_extrapolation_px=round(extrapolation_px, 1),
        estimated_position_error_m=round(error_m, 0),
        confidence=round(confidence, 2),
        notes=notes,
    )
