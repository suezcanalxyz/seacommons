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

# Total visible lifetime of an unresolved distress marker on Live. Concluded
# incidents leave Live immediately and remain available through archive/replay
# surfaces instead of occupying the current operational timeline.
DISTRESS_LIVE_MAX_AGE_DAYS = 7
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


_URL_RE = re.compile(r"https?://\S+", re.I)


def text_keywords(text: str) -> set[str]:
    """Significant lowercase words/hashtags (4+ chars) for cross-post matching.

    URLs are stripped first so the t.co slug of one post can never count as a
    shared keyword with a different post.
    """
    stripped_text = _URL_RE.sub(" ", text or "")
    return {
        stripped
        for word in re.findall(r"#?\w{4,}", stripped_text)
        if (stripped := word.strip("#.,!?:;").lower()) not in _KEYWORD_STOPWORDS
    }


def parse_utc(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


# A single shared keyword is not enough to say two posts are about the same
# incident: common domain vocabulary ("rescued", "distress", a frequently-
# mentioned place like "crete") recurs across many unrelated Alarm Phone
# reports. Two independent shared terms (e.g. a number + a name, or two
# specific place/vessel references) is a much stronger same-incident signal
# and was true of every real cross-post resolution case seen in practice.
_MIN_SHARED_KEYWORDS_FOR_RESOLUTION_MATCH = 2


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
        if len(event_kw & text_keywords(other.text or other.title)) >= _MIN_SHARED_KEYWORDS_FOR_RESOLUTION_MATCH:
            return True
    return False


def has_own_reply_resolution(event: IntelEvent) -> bool:
    """True if one of this event's own thread_reposts entries — a self-reply
    structurally verified (via X's own in_reply_to link + matching author,
    see twikit_monitor._check_self_replies) to answer THIS exact tweet, not a
    text-similarity guess across different posts — reads as a concluded
    outcome (e.g. "Rescued to #Lampedusa!").

    No keyword-overlap check needed here, unlike has_resolution_signal: the
    reply is already proven to be about this incident by X's own thread
    link, so there is no cross-incident false-match risk to guard against.
    """
    for repost in event.metadata.get("thread_reposts") or []:
        note = repost.get("note")
        if note and is_concluded_incident(str(note)):
            return True
    return False


def is_directly_concluded(event: IntelEvent) -> bool:
    """Whether this incident carries its own structurally reliable conclusion.

    This deliberately excludes fuzzy cross-post matching because callers that
    only have one event cannot safely infer relationships to other incidents.
    Direct text and same-author self-replies are sufficient to remove the most
    common Alarm Phone resolution path from Live immediately.
    """
    return is_concluded_incident(event.text or event.title) or has_own_reply_resolution(event)


def distress_lifecycle(event: IntelEvent, *, now: datetime, same_source: list[IntelEvent]) -> str:
    """'active' (red), 'resolved' (green) or 'archived' (gray).

    Callers must separately drop anything past DISTRESS_LIVE_MAX_AGE_DAYS —
    this only distinguishes among events still within that window.

    Deliberately does NOT trust a stored `incident_status` metadata field:
    that value (only ever set by alarm_phone_monitor.py, never by twikit) is
    frozen at ingestion time using whatever text-classification logic
    existed then — a classifier fix or improvement can never retroactively
    correct it, and a duplicate of the same tweet from a source that never
    set the field would silently disagree with one that did. Always
    recomputing from the event's own text keeps this consistent across
    sources and self-healing across classifier fixes.
    """
    if is_directly_concluded(event):
        return "resolved"
    if has_resolution_signal(event, same_source):
        return "resolved"
    observed = parse_utc(event.timestamp_utc)
    age_hours = (now - observed).total_seconds() / 3600 if observed else 0
    return "archived" if age_hours >= ARCHIVE_AFTER_HOURS else "active"


def is_within_live_window(event: IntelEvent, *, now: datetime) -> bool:
    """Whether a marker belongs on the current operational Live surface.

    A directly concluded incident is removed immediately. Unresolved cases
    remain bounded by the rolling seven-day window; older history belongs in
    archive/replay views. Cross-post conclusions are handled by callers that
    have the full same-source context.
    """
    if is_directly_concluded(event):
        return False
    observed = parse_utc(event.timestamp_utc)
    if observed is None:
        return True
    age_days = (now - observed).total_seconds() / 86400
    return age_days < DISTRESS_LIVE_MAX_AGE_DAYS
