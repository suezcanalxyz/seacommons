# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared distress-marker lifecycle logic.

Used by both core/api/routes/live.py (the VM-hosted public feed) and
core/live_edge_publisher.py (the Cloudflare edge push) so the two paths can
never silently diverge on what counts as active/resolved/archived — there is
exactly one place this policy is defined.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from core.intel.geoextract import is_concluded_incident
from core.intel.store import IntelEvent

# Total visible lifetime of a distress marker on Live, regardless of state.
DISTRESS_LIVE_MAX_AGE_DAYS = 3
# How far back to look for a later same-source post reporting resolution.
RESOLUTION_LOOKBACK_DAYS = 10
# Once an unresolved report has had no update for this long, it fades from
# "active" (red) to "archived" (gray) — no longer demanding attention, but
# not yet dropped from the map either.
ARCHIVE_AFTER_HOURS = 24

_KEYWORD_STOPWORDS = frozenset({
    "with", "from", "were", "have", "been", "that", "this", "they", "them",
    "their", "people", "group", "persons", "boat", "vessel", "distress",
    "alarm", "phone", "alarmphone", "still", "remain", "remains", "found",
    "hospitalised", "hospitalized", "informed", "authorities", "relatives",
})


def text_keywords(text: str) -> set[str]:
    """Significant lowercase words/hashtags (4+ chars) for cross-post matching."""
    return {
        stripped
        for word in re.findall(r"#?\w{4,}", text or "")
        if (stripped := word.strip("#.,!?:;").lower()) not in _KEYWORD_STOPWORDS
    }


def parse_utc(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def has_resolution_signal(event: IntelEvent, same_source: list[IntelEvent]) -> bool:
    """True if a later post from the same source reports this incident resolved."""
    event_time = parse_utc(event.timestamp_utc)
    event_kw = text_keywords(event.text or event.title)
    if event_time is None or not event_kw:
        return False
    for other in same_source:
        if other.id == event.id:
            continue
        other_time = parse_utc(other.timestamp_utc)
        if other_time is None or other_time <= event_time:
            continue
        if (other_time - event_time).days > RESOLUTION_LOOKBACK_DAYS:
            continue
        if not is_concluded_incident(other.text or other.title):
            continue
        if event_kw & text_keywords(other.text or other.title):
            return True
    return False


def distress_lifecycle(event: IntelEvent, *, now: datetime, same_source: list[IntelEvent]) -> str:
    """'active' (red), 'resolved' (green) or 'archived' (gray).

    Callers must separately drop anything past DISTRESS_LIVE_MAX_AGE_DAYS —
    this only distinguishes among events still within that window.
    """
    if str(event.metadata.get("incident_status") or "") == "resolved":
        return "resolved"
    if is_concluded_incident(event.text or event.title):
        return "resolved"
    if has_resolution_signal(event, same_source):
        return "resolved"
    observed = parse_utc(event.timestamp_utc)
    age_hours = (now - observed).total_seconds() / 3600 if observed else 0
    return "archived" if age_hours >= ARCHIVE_AFTER_HOURS else "active"


def is_within_live_window(event: IntelEvent, *, now: datetime) -> bool:
    """False once a distress marker exceeds its total Live lifetime."""
    observed = parse_utc(event.timestamp_utc)
    if observed is None:
        return True
    age_days = (now - observed).total_seconds() / 86400
    return age_days < DISTRESS_LIVE_MAX_AGE_DAYS
