"""Deterministic, versioned behavioural baselines from AIS track history."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from typing import Any

from core.mda.vessel_subject import subject_id_for

METHOD_VERSION = "vessel-behaviour-v1"
MIN_SAMPLE_COUNT = 20
MIN_HISTORY_DAYS = 3.0
ROUTE_CELL_DEG = 0.05
MIN_PORT_PAIR_SUPPORT = 2


@dataclass(frozen=True)
class BehaviouralBaseline:
    baseline_id: str
    subject_id: str
    primary_mmsi: str
    primary_imo: str | None
    window_start: datetime
    window_end: datetime
    sample_count: int
    history_days: float
    route_model: dict[str, Any]
    speed_model: dict[str, Any]
    port_model: dict[str, Any]
    silence_model: dict[str, Any]
    evidence_fingerprint: str
    method_version: str = METHOD_VERSION


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _percentile(values: list[float], q: float) -> float | None:
    clean = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    rank = (len(clean) - 1) * q
    lo, hi = int(math.floor(rank)), int(math.ceil(rank))
    if lo == hi:
        return clean[lo]
    weight = rank - lo
    return clean[lo] * (1 - weight) + clean[hi] * weight


def _load_tracks(mmsi: str, since: datetime, until: datetime) -> list[dict[str, Any]]:
    from core.vessels.track_store import track_store

    return track_store.track(mmsi, since=since, until=until, limit=5000)


def _registry_identity(mmsi: str) -> dict[str, Any]:
    from core.vessels.registry import registry

    return dict((getattr(registry, "_cache", {}) or {}).get(mmsi, {}) or {})


def _derive_port_calls(track: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from core.api.routes.mda import _derive_recent_port_calls

    return _derive_recent_port_calls(track, limit=32)


def _route_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cells: list[list[float]] = []
    seen: set[tuple[float, float]] = set()
    for row in rows:
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        cell = (round(round(lat / ROUTE_CELL_DEG) * ROUTE_CELL_DEG, 4), round(round(lon / ROUTE_CELL_DEG) * ROUTE_CELL_DEG, 4))
        if cell not in seen:
            seen.add(cell)
            cells.append([cell[0], cell[1]])
    return {"kind": "grid_corridor", "cell_deg": ROUTE_CELL_DEG, "cells": cells, "sample_count": len(rows)}


def _speed_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    speeds = []
    for row in rows:
        try:
            value = float(row.get("sog"))
        except (TypeError, ValueError):
            continue
        if 0.5 <= value <= 80:
            speeds.append(value)
    return {
        "sample_count": len(speeds),
        "p05": _percentile(speeds, 0.05),
        "p25": _percentile(speeds, 0.25),
        "p50": _percentile(speeds, 0.50),
        "p75": _percentile(speeds, 0.75),
        "p95": _percentile(speeds, 0.95),
    }


def _silence_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    times = [ts for ts in (_parse_ts(row.get("ts")) for row in rows) if ts is not None]
    times.sort()
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:]) if b > a]
    return {
        "sample_count": len(gaps),
        "p50_seconds": _percentile(gaps, 0.50),
        "p95_seconds": _percentile(gaps, 0.95),
        "max_seconds": max(gaps) if gaps else None,
        "coverage_caveat": "AIS receiver coverage and provider continuity can affect observed gaps",
    }


def _port_model(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    calls = _derive_port_calls(rows)
    ports = [str(call.get("port")) for call in calls if call.get("port")]
    port_counts = Counter(ports)
    pair_counts = Counter(zip(ports, ports[1:]))
    recurrent_ports = sorted(port for port, count in port_counts.items() if count >= 2)
    recurrent_pairs = [list(pair) for pair, count in sorted(pair_counts.items()) if count >= MIN_PORT_PAIR_SUPPORT]
    return {
        "call_count": len(calls),
        "recurrent_ports": recurrent_ports,
        "recurrent_pairs": recurrent_pairs,
        "pair_support": {f"{a}->{b}": count for (a, b), count in sorted(pair_counts.items())},
    }, calls


def _fingerprint(subject_id: str, window_start: datetime, window_end: datetime, rows: list[dict[str, Any]], calls: list[dict[str, Any]]) -> str:
    stable_rows = []
    for row in rows:
        stable_rows.append({
            "ts": str(row.get("ts") or ""), "lat": row.get("lat"), "lon": row.get("lon"),
            "sog": row.get("sog"), "nav_status": row.get("nav_status"), "source": row.get("source"),
        })
    payload = {
        "subject_id": subject_id,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "rows": stable_rows,
        "port_calls": calls,
        "method_version": METHOD_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def build_baseline(mmsi: str, *, window_days: int = 30, now: datetime | None = None) -> BehaviouralBaseline | None:
    end = now or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = end - timedelta(days=window_days)
    rows = sorted(_load_tracks(mmsi, start, end), key=lambda row: str(row.get("ts") or ""))
    parsed = [ts for ts in (_parse_ts(row.get("ts")) for row in rows) if ts is not None]
    if len(rows) < MIN_SAMPLE_COUNT or len(parsed) < 2:
        return None
    history_days = (max(parsed) - min(parsed)).total_seconds() / 86400.0
    if history_days < MIN_HISTORY_DAYS:
        return None
    identity = _registry_identity(mmsi)
    subject_id = subject_id_for(imo=identity.get("imo"), mmsi=mmsi)
    if subject_id is None:
        return None
    port_model, calls = _port_model(rows)
    fingerprint = _fingerprint(subject_id, start, end, rows, calls)
    baseline_id = "vbl:" + hashlib.sha256(f"{subject_id}|{start.isoformat()}|{end.isoformat()}|{METHOD_VERSION}|{fingerprint}".encode()).hexdigest()[:40]
    return BehaviouralBaseline(
        baseline_id=baseline_id, subject_id=subject_id, primary_mmsi=mmsi,
        primary_imo=str(identity.get("imo")) if identity.get("imo") else None,
        window_start=start, window_end=end, sample_count=len(rows), history_days=history_days,
        route_model=_route_model(rows), speed_model=_speed_model(rows), port_model=port_model,
        silence_model=_silence_model(rows), evidence_fingerprint=fingerprint,
    )


def _session_scope():
    from core.db.session import session_scope

    return session_scope()


def _from_row(row) -> BehaviouralBaseline:
    return BehaviouralBaseline(
        baseline_id=row.baseline_id,
        subject_id=row.subject_id,
        primary_mmsi=row.primary_mmsi,
        primary_imo=row.primary_imo,
        window_start=row.window_start,
        window_end=row.window_end,
        sample_count=row.sample_count,
        history_days=row.history_days,
        route_model=dict(row.route_model or {}),
        speed_model=dict(row.speed_model or {}),
        port_model=dict(row.port_model or {}),
        silence_model=dict(row.silence_model or {}),
        evidence_fingerprint=row.evidence_fingerprint,
        method_version=row.method_version,
    )


def persist_baseline(baseline: BehaviouralBaseline) -> BehaviouralBaseline:
    from core.db.models import VesselBehaviouralBaselineDB

    with _session_scope() as db:
        existing = db.get(VesselBehaviouralBaselineDB, baseline.baseline_id)
        if existing is not None:
            if existing.evidence_fingerprint != baseline.evidence_fingerprint:
                raise ValueError("baseline_id collision with different evidence fingerprint")
            return _from_row(existing)
        row = VesselBehaviouralBaselineDB(
            baseline_id=baseline.baseline_id,
            subject_id=baseline.subject_id,
            primary_mmsi=baseline.primary_mmsi,
            primary_imo=baseline.primary_imo,
            window_start=baseline.window_start,
            window_end=baseline.window_end,
            sample_count=baseline.sample_count,
            history_days=baseline.history_days,
            route_model=baseline.route_model,
            speed_model=baseline.speed_model,
            port_model=baseline.port_model,
            silence_model=baseline.silence_model,
            evidence_fingerprint=baseline.evidence_fingerprint,
            method_version=baseline.method_version,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.flush()
        return _from_row(row)


def latest_baseline(mmsi: str) -> BehaviouralBaseline | None:
    from core.db.models import VesselBehaviouralBaselineDB

    with _session_scope() as db:
        row = (
            db.query(VesselBehaviouralBaselineDB)
            .filter(VesselBehaviouralBaselineDB.primary_mmsi == mmsi)
            .order_by(VesselBehaviouralBaselineDB.window_end.desc(), VesselBehaviouralBaselineDB.created_at.desc())
            .first()
        )
        return _from_row(row) if row is not None else None
