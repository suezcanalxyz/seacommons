# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging-only, fail-closed temporal routing of reviewed maritime incidents.

No public endpoint, database access, mutation, or production publication.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("routing_event_clock_required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("routing_invalid_clock") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("routing_timezone_required")
    return dt.astimezone(timezone.utc)


def route_staging_incident(
    preview: Mapping[str, object],
    *,
    now_utc: str,
    corroborated: bool = False,
    reviewed: bool = False,
    active_update_at_utc: str | None = None,
) -> dict[str, object]:
    """Return a nonpublishable LIVE/PLAY proposal for a source-faithful preview.

    An active update may retain a previously occurring event in LIVE only if
    explicitly reviewed and timestamped within the last 24 hours.
    """
    now = _utc(now_utc)
    if not isinstance(preview, Mapping) or preview.get("staging_only") is not True or preview.get("publication_allowed") is not False:
        raise ValueError("routing_untrusted_preview")
    if type(corroborated) is not bool or type(reviewed) is not bool:
        raise ValueError("routing_invalid_review_flags")
    incident_type = preview.get("proposed_incident_type")
    if incident_type not in {"maritime_attack", "piracy"}:
        return {"destination": "review_queue", "reason": "not_an_attack", "publication_allowed": False, "staging_only": True}
    if not reviewed or not corroborated:
        return {"destination": "review_queue", "reason": "corroboration_or_review_missing", "publication_allowed": False, "staging_only": True}
    if preview.get("review_blockers"):
        return {"destination": "review_queue", "reason": "unresolved_review_blockers", "publication_allowed": False, "staging_only": True}
    event = _utc(preview.get("occurred_at_utc"))
    if event > now:
        raise ValueError("routing_future_event")
    location = preview.get("reported_location")
    if not isinstance(location, Mapping) or location.get("role") != "incident_site" or type(location.get("lat")) not in (int, float) or type(location.get("lon")) not in (int, float):
        return {"destination": "review_queue", "reason": "incident_location_unverified", "publication_allowed": False, "staging_only": True}
    if active_update_at_utc is not None:
        update = _utc(active_update_at_utc)
        if update < event or update > now:
            raise ValueError("routing_invalid_active_update")
    else:
        update = None
    recent = timedelta(hours=24)
    destination = "LIVE" if now - event <= recent or (update is not None and now - update <= recent) else "PLAY"
    return {
        "destination": destination, "reason": "recent_event" if now - event <= recent else ("recent_active_update" if destination == "LIVE" else "historical_event"),
        "publication_allowed": False, "staging_only": True,
        "canonical_observation_id": preview.get("canonical_observation_id"),
        "occurred_at_utc": event.isoformat(),
    }
