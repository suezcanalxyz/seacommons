# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evidence-safe AIS track discontinuity analysis.

A rendered straight line is NOT evidence of a sailed route. This module
only measures adjacent observed fixes; it never fabricates interpolated
locations or asserts a hidden port call or spoofing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt, isfinite

EARTH_KM = 6371.0088
KNOTS_PER_KMH = 1 / 1.852


def _utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None  # An unzoned timestamp must not be silently treated as UTC.
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _point(row: dict) -> dict | None:
    try:
        lat, lon = float(row["lat"]), float(row["lon"])
    except (TypeError, ValueError, KeyError):
        return None
    ts = _utc(row.get("ts"))
    if not ts or not all(map(isfinite, (lat, lon))) or abs(lat) > 90 or abs(lon) > 180:
        return None
    return {"ts": ts, "lat": lat, "lon": lon, "source": str(row.get("source") or "unknown")}


def _distance_km(a: dict, b: dict) -> float:
    lat1, lat2 = radians(a["lat"]), radians(b["lat"])
    dlat = lat2 - lat1
    dlon = radians(b["lon"] - a["lon"])
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_KM * asin(min(1, sqrt(max(0, h))))


def analyze_track_discontinuities(
    track: list[dict], *, min_gap_minutes: float = 30,
    speed_threshold_knots: float = 45, limit: int = 100,
) -> dict:
    """Classify evidence gaps and physically implausible AIS jumps.

    Preserve original track order to flag out-of-order ingestion. A zero or
    negative time delta is not a valid speed estimate. Source labels identify
    provider provenance, NOT independent corroboration.
    """
    valid = [_point(row) for row in track if isinstance(row, dict)]
    valid = [row for row in valid if row is not None]
    segments: list[dict] = []
    invalid_order = 0
    for a, b in zip(valid, valid[1:]):
        delta_s = (b["ts"] - a["ts"]).total_seconds()
        if delta_s <= 0:
            invalid_order += 1
            continue
        distance = _distance_km(a, b)
        implied_knots = distance / (delta_s / 3600) * KNOTS_PER_KMH
        gap = delta_s >= min_gap_minutes * 60
        jump = implied_knots > speed_threshold_knots
        if not (gap or jump):
            continue
        segments.append({
            "start": {"ts": a["ts"].isoformat(), "lat": a["lat"], "lon": a["lon"],
                      "source": a["source"]},
            "end": {"ts": b["ts"].isoformat(), "lat": b["lat"], "lon": b["lon"],
                    "source": b["source"]},
            "elapsed_seconds": round(delta_s, 1),
            "distance_km": round(distance, 2),
            "implied_speed_knots": round(implied_knots, 1),
            "classification": "physically_implausible_jump" if jump else "unobserved_interval",
            "is_observed_route": False,
            "evidence_level": "adjacent_ais_fixes_only",
            "port_call": "not_established",
            "spoofing": "not_established",
            "requires_raw_message_timestamps": True,
            "independent_corroboration": "not_established",
        })
    return {
        "method": "adjacent_fix_geodesic_v1",
        "valid_fix_count": len(valid),
        "out_of_order_pairs": invalid_order,
        "thresholds": {"min_gap_minutes": min_gap_minutes,
                       "implied_speed_knots": speed_threshold_knots},
        "segments": segments[-limit:],
        "total_flagged_segments": len(segments),
        "caveat": ("A straight map segment between AIS fixes is a visualization, not an "
                   "observed route. Third-party playback cursor times are not AIS timestamps. "
                   "No port call or deliberate AIS manipulation is inferred."),
    }
