# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared distress-marker lifecycle logic.

Used by both core/api/routes/live.py (the VM-hosted public feed) and
core/live_edge_publisher.py (the Cloudflare edge push) so the two paths can
never silently diverge on what counts as active/resolved/archived — there is
exactly one place this policy is defined.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.domain.live_contracts import IncidentLifecycle
from core.intel.geoextract import is_concluded_incident, is_ongoing_incident
from core.intel.store import IntelEvent

# Total visible lifetime of an unresolved distress marker on Live. Concluded
# incidents leave Live immediately and remain available through archive/replay
# surfaces instead of occupying the current operational timeline.
DISTRESS_LIVE_MAX_AGE_HOURS = 24
# Compatibility for bounded DB scans that accept integer days.
DISTRESS_LIVE_MAX_AGE_DAYS = 1
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


def has_resolution_signal(
    event: IntelEvent, same_source: list[IntelEvent], *, now: Optional[datetime] = None,
) -> bool:
    """True if a credible later same-source post reports resolution."""
    event_time = parse_utc(event.timestamp_utc)
    event_kw = text_keywords(event.text or event.title)
    future_limit = _future_limit(now) if now is not None else None
    if event_time is None or not event_kw:
        return False
    # Consider the latest *decisive* matched follow-up, not the first rescue
    # found in an arbitrarily ordered source feed. A later credible distress
    # update can reopen a case; an ambiguous acknowledgement cannot.
    latest_decisive: Optional[tuple[datetime, str]] = None
    for other in same_source:
        if other.id == event.id:
            continue
        other_time = parse_utc(other.timestamp_utc)
        if other_time is None or other_time <= event_time:
            continue
        if future_limit is not None and other_time > future_limit:
            continue
        if other_time - event_time > timedelta(days=RESOLUTION_LOOKBACK_DAYS):
            continue
        other_text = other.text or other.title
        if len(event_kw & text_keywords(other_text)) < _MIN_SHARED_KEYWORDS_FOR_RESOLUTION_MATCH:
            continue
        outcome = _outcome_from_text(other_text)
        if outcome is None:
            continue
        if latest_decisive is None or other_time > latest_decisive[0]:
            latest_decisive = (other_time, outcome)
    return latest_decisive is not None and latest_decisive[1] == IncidentLifecycle.RESOLVED.value


def has_own_reply_resolution(event: IntelEvent) -> bool:
    """True if the latest decisive self-reply says the incident is resolved.

    Replies are structurally verified through X's ``in_reply_to`` link and
    matching author. A later ongoing-danger reply therefore reopens an event
    that an earlier reply had marked resolved.
    """
    return latest_own_reply_outcome(event) == IncidentLifecycle.RESOLVED.value


def _outcome_from_text(text: str) -> Optional[str]:
    """Return a decisive lifecycle outcome, or None for an ambiguous update."""
    if is_ongoing_incident(text):
        return IncidentLifecycle.ACTIVE.value
    if is_concluded_incident(text):
        return IncidentLifecycle.RESOLVED.value
    return None


def _future_limit(now: datetime) -> datetime:
    """Upper bound for a source timestamp, including small clock skew."""
    now_utc = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    return now_utc + timedelta(minutes=5)


def latest_own_reply_outcome(
    event: IntelEvent, *, now: Optional[datetime] = None,
) -> Optional[str]:
    """Outcome of the latest credible textual self-reply, allowing reopen.

    The same temporal gate used by Live retention must govern lifecycle
    decisions: a future-dated reply cannot prematurely resolve or reopen a
    case. Undated/malformed provider entries are not lifecycle evidence when
    an evaluation clock is supplied; they remain in the underlying record.
    """
    future_limit = _future_limit(now) if now is not None else None
    replies = [
        repost for repost in (event.metadata.get("thread_reposts") or [])
        if isinstance(repost, dict)
        and (
            future_limit is None
            or (
                (posted := parse_utc(str(repost.get("posted_at") or ""))) is not None
                and posted <= future_limit
            )
        )
    ]
    replies.sort(
        key=lambda repost: parse_utc(str(repost.get("posted_at") or ""))
        or datetime.min.replace(tzinfo=timezone.utc),
    )
    textual_replies = [
        str(repost.get("note") or "").strip()
        for repost in replies
        if str(repost.get("note") or "").strip()
    ]
    if not textual_replies:
        return None
    # An ambiguous acknowledgement must not erase an earlier decisive rescue
    # or danger update. Only a later *decisive* reply can change the outcome.
    for note in reversed(textual_replies):
        outcome = _outcome_from_text(note)
        if outcome is not None:
            return outcome
    return IncidentLifecycle.NEEDS_REVIEW.value


def _latest_activity_time(
    event: IntelEvent, *, now: Optional[datetime] = None,
) -> Optional[datetime]:
    """Latest credible observation, excluding source-clock timestamps in the future.

    A malformed repost dated years ahead must not keep a humanitarian distress
    in the rolling Live window indefinitely. Keep valid older observations
    rather than allowing a single bad update to hide an otherwise fresh case.
    """
    timestamps = [parse_utc(event.timestamp_utc)]
    timestamps.extend(
        parse_utc(str(repost.get("posted_at") or ""))
        for repost in event.metadata.get("thread_reposts") or []
        if isinstance(repost, dict)
    )
    timestamps.append(parse_utc(str(event.metadata.get("last_repost_at") or "")))
    observed = [value for value in timestamps if value is not None]
    if now is not None:
        now_utc = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
        future_limit = now_utc + timedelta(minutes=5)
        observed = [value for value in observed if value <= future_limit]
    return max(observed) if observed else None


def is_directly_concluded(
    event: IntelEvent, *, now: Optional[datetime] = None,
) -> bool:
    """Whether this incident carries its own structurally reliable conclusion.

    A later explicit danger update can reopen a concluded case. An ambiguous
    self-reply cannot erase a final outcome already stated in the founding
    report; it only requests review when the founding report itself remains
    open or ambiguous.
    """
    original_outcome = _outcome_from_text(event.text or event.title)
    reply_outcome = latest_own_reply_outcome(event, now=now)
    if reply_outcome == IncidentLifecycle.ACTIVE.value:
        return False
    if reply_outcome == IncidentLifecycle.RESOLVED.value:
        return True
    if original_outcome == IncidentLifecycle.RESOLVED.value:
        return True
    return False


def distress_lifecycle(event: IntelEvent, *, now: datetime, same_source: list[IntelEvent]) -> str:
    """Return active, resolved, archived, or needs_review lifecycle state.

    Callers must separately drop anything past DISTRESS_LIVE_MAX_AGE_HOURS —
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
    original_outcome = _outcome_from_text(event.text or event.title)
    state = original_outcome or IncidentLifecycle.ACTIVE.value
    reply_outcome = latest_own_reply_outcome(event, now=now)
    if reply_outcome == IncidentLifecycle.ACTIVE.value:
        state = IncidentLifecycle.ACTIVE.value
    elif reply_outcome == IncidentLifecycle.RESOLVED.value:
        state = IncidentLifecycle.RESOLVED.value
    elif reply_outcome == IncidentLifecycle.NEEDS_REVIEW.value:
        # Do not let a non-decisive comment overwrite a known final outcome.
        if original_outcome != IncidentLifecycle.RESOLVED.value:
            state = IncidentLifecycle.NEEDS_REVIEW.value
    elif has_resolution_signal(event, same_source, now=now):
        state = IncidentLifecycle.RESOLVED.value
    if state in {IncidentLifecycle.RESOLVED.value, IncidentLifecycle.NEEDS_REVIEW.value}:
        return state
    observed = _latest_activity_time(event, now=now)
    age_hours = (now - observed).total_seconds() / 3600 if observed else 0
    return (
        IncidentLifecycle.ARCHIVED.value
        if age_hours >= ARCHIVE_AFTER_HOURS
        else IncidentLifecycle.ACTIVE.value
    )


def is_within_live_retention_window(event: IntelEvent, *, now: datetime) -> bool:
    """Whether an event belongs to the rolling 24-hour Live timeline.

    Retention is intentionally independent from operational state. A resolved
    or outcome-unknown incident can remain visible in Live until the end of
    the 24-hour window, while downstream response/drift logic can still stop
    treating it as active immediately.
    """
    observed = _latest_activity_time(event, now=now)
    if observed is None:
        # No credible timestamp: do not advertise a case as currently Live.
        return False
    age_hours = (now - observed).total_seconds() / 3600
    return age_hours < DISTRESS_LIVE_MAX_AGE_HOURS


def is_within_live_window(event: IntelEvent, *, now: datetime) -> bool:
    """Whether a marker is still operationally active on Live.

    This preserves the stricter active-state semantic used by response/drift
    internals. Public timeline retention should use
    is_within_live_retention_window instead.
    """
    if is_directly_concluded(event, now=now):
        return False
    return is_within_live_retention_window(event, now=now)
