"""Explainable comparison of current vessel behaviour against a stored baseline."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any

from core.mda.behavioural_baseline import BehaviouralBaseline

ROUTE_DEVIATION_THRESHOLD_NM = 8.0
SPEED_HIGH_MULTIPLIER = 1.20
SPEED_LOW_MULTIPLIER = 0.50
SILENCE_P95_MULTIPLIER = 1.50
SILENCE_MIN_EXCESS_S = 900.0
BASELINE_STALE_DAYS = 14.0


@dataclass(frozen=True)
class BehaviourAssessment:
    status: str
    baseline_id: str | None
    method_version: str | None
    reason_codes: tuple[str, ...]
    dimensions: dict[str, Any]
    caveats: tuple[str, ...]
    evaluated_at: datetime


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_nm = 3440.065
    a1, a2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dlon / 2) ** 2
    return r_nm * 2 * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _route_dimension(track: list[dict[str, Any]], baseline: BehaviouralBaseline) -> tuple[dict[str, Any], str | None]:
    cells = baseline.route_model.get("cells") or []
    points = [(row.get("lat"), row.get("lon")) for row in track if row.get("lat") is not None and row.get("lon") is not None]
    if not cells or not points:
        return {"status": "unavailable", "caveat": "route evidence unavailable"}, None
    lat, lon = map(float, points[-1])
    distance = min(_distance_nm(lat, lon, float(cell[0]), float(cell[1])) for cell in cells)
    threshold = max(ROUTE_DEVIATION_THRESHOLD_NM, float(baseline.route_model.get("cell_deg") or 0.05) * 60 * 2)
    unusual = distance > threshold
    return {"status": "unusual" if unusual else "expected", "distance_nm": round(distance, 3), "threshold_nm": round(threshold, 3)}, ("ROUTE_DEVIATION" if unusual else None)


def _speed_dimension(track: list[dict[str, Any]], baseline: BehaviouralBaseline) -> tuple[dict[str, Any], str | None]:
    values = []
    for row in track:
        try:
            value = float(row.get("sog"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    p05, p95 = baseline.speed_model.get("p05"), baseline.speed_model.get("p95")
    if not values or p05 is None or p95 is None:
        return {"status": "unavailable", "caveat": "speed evidence unavailable"}, None
    observed = values[-1]
    low, high = float(p05) * SPEED_LOW_MULTIPLIER, float(p95) * SPEED_HIGH_MULTIPLIER
    unusual = observed < low or observed > high
    return {"status": "unusual" if unusual else "expected", "observed_kn": round(observed, 3), "lower_kn": round(low, 3), "upper_kn": round(high, 3)}, ("UNUSUAL_SPEED_PROFILE" if unusual else None)


def _silence_dimension(track: list[dict[str, Any]], baseline: BehaviouralBaseline) -> tuple[dict[str, Any], str | None]:
    times = [ts for ts in (_parse_ts(row.get("ts")) for row in track) if ts is not None]
    times.sort()
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:]) if b > a]
    p95 = baseline.silence_model.get("p95_seconds")
    if not gaps or p95 is None:
        return {"status": "unavailable", "caveat": "silence evidence unavailable"}, None
    observed = max(gaps)
    threshold = max(float(p95) * SILENCE_P95_MULTIPLIER, float(p95) + SILENCE_MIN_EXCESS_S)
    unusual = observed > threshold
    return {"status": "unusual" if unusual else "expected", "observed_gap_seconds": observed, "threshold_seconds": threshold}, ("UNUSUAL_AIS_SILENCE" if unusual else None)


def _port_dimension(track: list[dict[str, Any]], baseline: BehaviouralBaseline) -> tuple[dict[str, Any], str | None]:
    ports = [str(row.get("port")) for row in track if row.get("port")]
    compact = [port for index, port in enumerate(ports) if index == 0 or port != ports[index - 1]]
    if len(compact) < 2:
        return {"status": "unavailable", "caveat": "current port-pair evidence unavailable"}, None
    pair = compact[-2:]
    recurrent = baseline.port_model.get("recurrent_pairs") or []
    if not recurrent:
        return {"status": "unavailable", "caveat": "baseline port-pair evidence unavailable", "observed_pair": pair}, None
    unusual = pair not in recurrent
    return {"status": "unusual" if unusual else "expected", "observed_pair": pair, "recurrent_pairs": recurrent}, ("UNUSUAL_PORT_PAIR" if unusual else None)


def assess_behaviour(track: list[dict[str, Any]], baseline: BehaviouralBaseline | None, *, evaluated_at: datetime | None = None) -> BehaviourAssessment:
    now = evaluated_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if baseline is None:
        return BehaviourAssessment("insufficient_history", None, None, ("INSUFFICIENT_HISTORY",), {}, ("No usable behavioural baseline",), now)
    dimensions: dict[str, Any] = {}
    reasons: list[str] = []
    for name, fn in (("route", _route_dimension), ("speed", _speed_dimension), ("port_pair", _port_dimension), ("silence", _silence_dimension)):
        dimension, reason = fn(track, baseline)
        dimensions[name] = dimension
        if reason:
            reasons.append(reason)
    caveats = []
    window_end = baseline.window_end if baseline.window_end.tzinfo else baseline.window_end.replace(tzinfo=timezone.utc)
    stale_days = max(0.0, (now - window_end).total_seconds() / 86400.0)
    dimensions["baseline"] = {"window_end": window_end.isoformat(), "stale_days": round(stale_days, 3), "stale": stale_days > BASELINE_STALE_DAYS}
    if stale_days > BASELINE_STALE_DAYS:
        caveats.append("Baseline is stale relative to evaluation time")
    status = "unusual" if reasons else "expected"
    return BehaviourAssessment(status, baseline.baseline_id, baseline.method_version, tuple(reasons), dimensions, tuple(caveats), now)
