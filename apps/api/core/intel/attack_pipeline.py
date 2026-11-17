# SPDX-License-Identifier: AGPL-3.0-or-later
"""Review-only maritime attack report ↔ AIS context episodes.

RSS publication time is not treated as attack occurrence time. The pipeline
only records identity/track context for human review and never auto-publishes.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from core.intel.lifecycle import parse_utc


def _subject(row: dict[str, Any]) -> tuple[str | None, str | None]:
    provenance = dict(row.get("provenance") or {})
    mmsi = str(provenance.get("mmsi") or "").strip() or None
    imo = str(provenance.get("imo") or "").strip() or None
    return mmsi, imo


def _row_time(row: dict[str, Any]) -> datetime | None:
    return parse_utc(str(row.get("observed_at") or ""))


def _episode_id(subject_key: str, day: str) -> str:
    digest = hashlib.blake2s(f"{subject_key}|{day}".encode(), digest_size=12).hexdigest()
    return f"episode:reported-attack-context:{digest}"


def build_attack_context_feature(
    report_rows: list[dict[str, Any]],
    track_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build one internal episode from same-subject reports in one UTC day."""
    reports = [row for row in report_rows if _row_time(row) is not None]
    if not reports:
        return None
    reports.sort(key=lambda row: _row_time(row) or datetime.max.replace(tzinfo=timezone.utc))
    mmsi, imo = _subject(reports[0])
    if not mmsi and not imo:
        return None
    subject_key = f"mmsi:{mmsi}" if mmsi else f"imo:{imo}"
    subject_ids = [f"subj:{subject_key}"]
    if mmsi and imo:
        subject_ids.append(f"subj:imo:{imo}")

    times = [_row_time(row) for row in reports]
    times = [value for value in times if value is not None]
    first_at, last_at = min(times), max(times)
    groups = sorted({
        str((row.get("provenance") or {}).get("independence_group") or "").strip()
        for row in reports
        if str((row.get("provenance") or {}).get("independence_group") or "").strip()
    })
    observation_ids = sorted({
        str(row.get("observation_id") or "") for row in reports if row.get("observation_id")
    })

    nearest_offset_min = None
    if track_rows:
        deltas = []
        for track in track_rows:
            track_at = parse_utc(str(track.get("ts") or ""))
            if track_at is None:
                continue
            deltas.append(abs((track_at - last_at).total_seconds()) / 60.0)
        if deltas:
            nearest_offset_min = round(min(deltas), 3)

    explicit = next(
        (row for row in reports if row.get("lat") is not None and row.get("lon") is not None),
        None,
    )
    geometry = None
    if explicit is not None:
        geometry = {
            "type": "Point",
            "coordinates": [float(explicit["lon"]), float(explicit["lat"])],
        }

    verification = "multi_source_observed" if len(groups) >= 2 else "single_source_observed"
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "episode_id": _episode_id(subject_key, first_at.date().isoformat()),
            "episode_family": "reported_attack_context",
            "subject_ids": subject_ids,
            "observation_ids": observation_ids,
            "feature_ids": [],
            "first_observed_at": first_at.isoformat(),
            "last_observed_at": last_at.isoformat(),
            "timestamp_utc": last_at.isoformat(),
            "independence_groups": groups,
            "verification_status": verification,
            "episode_method_version": "reported-attack-context-v1",
            "analysis_state": "observation",
            "publication_state": "internal",
            "resolution_state": "open",
            "episode_status": "active",
            "behaviour_context": {
                "report_kind": "possible_maritime_attack",
                "report_count": len(reports),
                "track_context_fix_count": len(track_rows),
                "closest_track_to_publication_minutes": nearest_offset_min,
                "report_time_basis": "rss_publication_time_not_attack_occurrence_time",
                "explicit_report_coordinates": explicit is not None,
                "attack_confirmed": False,
                "publication_allowed": False,
                "requires_operator_review": True,
            },
            "alternative_explanations": [
                "RSS publication time may differ from the reported incident occurrence time.",
                "AIS availability and gaps can reflect receiver coverage, source outages, or transponder behaviour.",
            ],
        },
    }


def _snapshot(row) -> dict[str, Any]:
    return {
        "observation_id": row.observation_id,
        "observed_at": row.observed_at,
        "lat": row.lat,
        "lon": row.lon,
        "subject_refs": list(row.subject_refs or []),
        "provenance": dict(row.provenance or {}),
    }


def refresh_recent_attack_contexts(*, limit: int = 100, now: datetime | None = None) -> dict[str, int]:
    """Persist bounded review-only episodes from recent security RSS observations."""
    from core.db.models import SourceObservationDB
    from core.db.session import session_scope
    from core.intel.episode_store import save_episode
    from core.vessels.track_store import track_store

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now - timedelta(days=7)
    with session_scope() as db:
        rows = (
            db.query(SourceObservationDB)
            .filter(
                SourceObservationDB.service == "maritime",
                SourceObservationDB.lane == "security",
                SourceObservationDB.observation_type == "source_post",
                SourceObservationDB.received_at >= cutoff.replace(tzinfo=None),
            )
            .order_by(SourceObservationDB.received_at.desc())
            .limit(max(1, min(int(limit), 500)))
            .all()
        )
        snapshots = [_snapshot(row) for row in rows]

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in snapshots:
        mmsi, imo = _subject(row)
        subject_key = f"mmsi:{mmsi}" if mmsi else (f"imo:{imo}" if imo else "")
        observed = _row_time(row)
        if not subject_key or observed is None:
            continue
        groups.setdefault((subject_key, observed.date().isoformat()), []).append(row)

    report = {"scanned": len(snapshots), "groups": len(groups), "saved": 0, "with_track_context": 0}
    for (_subject_key, _day), report_rows in groups.items():
        mmsi, _imo = _subject(report_rows[0])
        times = [_row_time(row) for row in report_rows]
        times = [value for value in times if value is not None]
        tracks = []
        if mmsi and times:
            tracks = track_store.track(
                mmsi,
                since=min(times) - timedelta(hours=6),
                until=max(times) + timedelta(hours=1),
                limit=500,
            )
        feature = build_attack_context_feature(report_rows, tracks)
        if feature is None:
            continue
        save_episode(feature)
        report["saved"] += 1
        if tracks:
            report["with_track_context"] += 1
    return report
