"""Deterministic vessel-context projection over existing canonical inputs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from core.mda.vessel_subject import subject_id_for


def _registry_row(mmsi: str) -> dict[str, Any]:
    from core.vessels.registry import registry

    return dict((getattr(registry, "_cache", {}) or {}).get(mmsi, {}) or {})


def _track(mmsi: str, since: datetime) -> list[dict[str, Any]]:
    from core.vessels.track_store import track_store

    return track_store.track(mmsi, since=since, limit=5000)


def _recent_port_calls(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from core.api.routes.mda import _derive_recent_port_calls

    return _derive_recent_port_calls(rows)


def build_vessel_context(mmsi: str, *, hours: float = 24 * 30) -> dict[str, Any]:
    row = _registry_row(mmsi)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = _track(mmsi, since)
    subject_id = subject_id_for(imo=row.get("imo"), mmsi=mmsi)
    labels: list[dict[str, str]] = []
    if len(rows) >= 3:
        labels.append({"code": "RECURRENT_HISTORY_AVAILABLE", "evidence_level": "derived"})
    return {
        "subject_id": subject_id,
        "mmsi": mmsi,
        "static": {
            "name": row.get("ship_name"),
            "imo": row.get("imo"),
            "ship_type": row.get("ship_type"),
            "flag": row.get("flag"),
            "destination": row.get("destination"),
        },
        "history": {
            "window_hours": hours,
            "sample_count": len(rows),
            "first_seen_at": rows[0].get("ts") if rows else None,
            "last_seen_at": rows[-1].get("ts") if rows else None,
        },
        "recent_port_calls": _recent_port_calls(rows),
        "context_labels": labels,
    }
