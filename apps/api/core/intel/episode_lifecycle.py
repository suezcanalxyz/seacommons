# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure lifecycle decisions for persistent episodes shared by LIVE and PLAY.

This module intentionally does not write to the database or synthesize evidence.
Integration with episode persistence and API projections is a separate step.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

PLAY_DELAY = timedelta(hours=24)
TERMINAL_STATES = frozenset({"resolved", "archived"})
# "outcome_unknown" is an epistemic label, not proof that a case remains active.
# Keeping old unknown-outcome archive entries on LIVE would silently imply
# ongoing distress/security activity and flood the current map.
ACTIVE_STATES = frozenset({"detected", "active", "open", "needs_review"})


def utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("expected datetime")
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def play_eligible(*, detected_at: datetime, now: datetime) -> bool:
    """PLAY eligibility never depends on the resolution state."""
    return utc(now) >= utc(detected_at) + PLAY_DELAY


def visible_in_live(*, detected_at: datetime, status: str, now: datetime) -> bool:
    """Recent episodes and older active episodes remain visible in LIVE."""
    return status in ACTIVE_STATES or utc(now) < utc(detected_at) + PLAY_DELAY


def elapsed_seconds(*, started_at: datetime, ended_at: datetime | None, now: datetime) -> int:
    """A running clock is display arithmetic, not a new observation."""
    end = utc(ended_at) if ended_at is not None else utc(now)
    duration = (end - utc(started_at)).total_seconds()
    if duration < 0:
        raise ValueError("end cannot precede start")
    return int(duration)


def reconcile_gap(
    current: dict[str, Any],
    *,
    observation_id: str,
    observed_at: datetime,
    coordinates: tuple[float, float],
) -> dict[str, Any]:
    """Close an active gap only on a later, valid, new AIS observation.

    Coordinates are (longitude, latitude). Caller must verify AIS identity,
    source quality and authenticity before invoking this function.
    """
    if current.get("status") not in ACTIVE_STATES:
        return dict(current)
    if not observation_id:
        raise ValueError("observation_id required")
    lon, lat = coordinates
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("invalid coordinates")
    origin = current.get("origin")
    if not isinstance(origin, dict) or not isinstance(origin.get("observed_at"), datetime):
        raise ValueError("origin observation required")
    if utc(observed_at) <= utc(origin["observed_at"]):
        return dict(current)
    if observation_id in current.get("observation_ids", ()):
        return dict(current)
    result = dict(current)
    result["status"] = "resolved"
    result["ended_at"] = utc(observed_at)
    result["endpoint"] = {
        "observed_at": utc(observed_at),
        "observation_id": observation_id,
        "coordinates": [lon, lat],
        "kind": "observed",
    }
    result["observation_ids"] = [*current.get("observation_ids", ()), observation_id]
    return result


def public_episode_clock(item: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Annotate an already-public case without changing its publication policy."""
    from core.intel.lifecycle import parse_utc

    result = dict(item)
    detected = parse_utc(str(item.get("reported_at") or ""))
    if detected is None:
        return result
    status = str(item.get("incident_status") or "outcome_unknown").lower()
    ongoing = status in ACTIVE_STATES
    ended = parse_utc(str(item.get("resolved_at") or "")) if not ongoing else None
    if ended is not None and ended < detected:
        ended = None
    result["play_eligible_at"] = (utc(detected) + PLAY_DELAY).isoformat()
    result["play_eligible"] = play_eligible(detected_at=detected, now=now)
    result["ongoing"] = ongoing
    # Unknown outcome without an observed closure is neither a verified active
    # timer nor a measured incident duration. Do not manufacture one.
    result["elapsed_seconds"] = (
        elapsed_seconds(started_at=detected, ended_at=ended, now=now)
        if ongoing or ended is not None else None
    )
    return result
