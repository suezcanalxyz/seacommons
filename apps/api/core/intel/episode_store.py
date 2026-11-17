# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistence boundary for derived MaritimeEpisode records."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

_METHOD_VERSION = "maritime-episode-v1"


def episode_fingerprint(
    *,
    subject_ids: tuple[str, ...],
    family: str,
    signal_ids: tuple[str, ...],
    first_observed_at: str,
    last_observed_at: str,
    method_version: str = _METHOD_VERSION,
) -> str:
    payload = {
        "subject_ids": sorted(str(v) for v in subject_ids),
        "family": str(family),
        "signal_ids": sorted(str(v) for v in signal_ids),
        "first_observed_at": str(first_observed_at),
        "last_observed_at": str(last_observed_at),
        "method_version": str(method_version),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _parse_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _utc(value: datetime) -> datetime:
    """Normalize SQLAlchemy's naive UTC and incoming aware timestamps."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _ordered_union(previous: Any, incoming: Any) -> list[str]:
    return list(dict.fromkeys(
        str(value) for value in (*list(previous or ()), *list(incoming or ())) if str(value)
    ))


def merge_episode_values(existing: Any, incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge evidence for an unchanged canonical ID without rewinding history.

    This does NOT decide identity, verify new AIS positions, or publish cases.
    A replayed older snapshot may add evidence but must not regress the
    position, status or publication decision of a newer persisted snapshot.
    """
    values = dict(incoming)
    was_last = _utc(existing.end_at)
    new_last = _utc(values["end_at"])
    stale = new_last < was_last
    first = min(_utc(existing.start_at), _utc(values["start_at"]))
    last = max(was_last, new_last)
    values["start_at"] = first
    values["end_at"] = last
    for field in ("observation_ids", "feature_ids", "independence_groups", "alternative_explanations"):
        values[field] = _ordered_union(getattr(existing, field), values.get(field))

    context = dict(existing.behaviour_context or {})
    if not stale:
        context.update(values.get("behaviour_context") or {})
    values["behaviour_context"] = context
    if stale:
        for field in ("geometry", "status", "verification_status", "method_version"):
            values[field] = getattr(existing, field)
    # An already closed episode cannot silently become active again. A new
    # episode after verified reappearance must have its own episode identity.
    if str(existing.status) in {"resolved", "archived"} and values["status"] in {"detected", "active", "open"}:
        values["status"] = existing.status
    values["evidence_fingerprint"] = episode_fingerprint(
        subject_ids=tuple(str(v) for v in existing.subject_ids or ()),
        family=existing.episode_family,
        signal_ids=tuple(values["observation_ids"]),
        first_observed_at=first.isoformat(),
        last_observed_at=last.isoformat(),
        method_version=values["method_version"],
    )
    return values


def save_episode(feature: dict[str, Any]):
    from core.db.models import MaritimeEpisodeDB
    from core.db.session import session_scope

    props = feature.get("properties") or {}
    episode_id = str(props.get("episode_id") or "")
    family = str(props.get("episode_family") or "")
    subject_ids = tuple(str(v) for v in (props.get("subject_ids") or ()) if v)
    signal_ids = tuple(str(v) for v in (props.get("observation_ids") or props.get("related_signal_ids") or ()) if v)
    first_at = str(props.get("first_observed_at") or props.get("timestamp_utc") or "")
    last_at = str(props.get("last_observed_at") or props.get("timestamp_utc") or "")
    if not episode_id or not family or not subject_ids or not first_at or not last_at:
        raise ValueError("episode feature missing deterministic identity fields")

    method_version = str(props.get("episode_method_version") or _METHOD_VERSION)
    fingerprint = episode_fingerprint(
        subject_ids=subject_ids,
        family=family,
        signal_ids=signal_ids,
        first_observed_at=first_at,
        last_observed_at=last_at,
        method_version=method_version,
    )
    behaviour_context = dict(props.get("behaviour_context") or {})
    behaviour_context["analysis"] = {
        "analysis_state": str(props.get("analysis_state") or "observation"),
        "publication_state": str(props.get("publication_state") or "internal"),
        "resolution_state": str(props.get("resolution_state") or "open"),
        "lineage_ids": list(props.get("lineage_ids") or props.get("independence_groups") or ()),
    }
    values = {
        "episode_family": family,
        "subject_ids": list(subject_ids),
        "start_at": _parse_datetime(first_at),
        "end_at": _parse_datetime(last_at),
        "geometry": feature.get("geometry"),
        "observation_ids": list(signal_ids),
        "feature_ids": list(props.get("feature_ids") or ()),
        "independence_groups": list(props.get("independence_groups") or ()),
        "verification_status": str(props.get("verification_status") or "single_source_observed"),
        "behaviour_context": behaviour_context,
        "alternative_explanations": list(props.get("alternative_explanations") or ()),
        "evidence_fingerprint": fingerprint,
        "method_version": method_version,
        "status": str(props.get("episode_status") or "active"),
    }
    with session_scope() as db:
        row = db.query(MaritimeEpisodeDB).filter(MaritimeEpisodeDB.episode_id == episode_id).first()
        if row is None:
            row = MaritimeEpisodeDB(episode_id=episode_id, **values)
            db.add(row)
        else:
            if row.episode_family != family or tuple(row.subject_ids or ()) != subject_ids:
                raise ValueError("episode identity collision")
            merged = merge_episode_values(row, values)
            for key, value in merged.items():
                setattr(row, key, value)
        db.flush()
        db.refresh(row)
        db.expunge(row)
        return row
