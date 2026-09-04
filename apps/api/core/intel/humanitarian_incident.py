# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical HumanitarianIncident sync (docs/updates.md P0.3).

**Goal:** make HumanitarianIncident a stable incident object independent
of any one source post, owning current operational state (lifecycle,
when it last changed, when/if it resolved or archived).

v0 scope, honestly bounded: ``incident_id`` is 1:1 with the IntelEvent id
that created it. No cross-source correlation exists yet (docs/updates.md
P2.1, a later packet in this same dependency graph), so two independently
-reported posts about the same real-world case still become two separate
incident rows here -- this module does not claim to fix that; it adds
the persisted state_changed_at/resolved_at/archived_at timestamps that
did not exist anywhere before (docs/updates.md P0.1's audit flagged
their absence as unavailable), computed from real lifecycle transitions.

Wired additively via core.intel.store.intel_store's existing subscriber
fan-out (core.intel.fusion already uses the same hook) -- never replaces
core.intel.lifecycle.distress_lifecycle() as the read-time authority
feed.py/live_edge_publisher.py use; this is a parallel, persisted shadow
that a later packet can promote to authoritative once correlation (P2.1)
and the full evidence-based lifecycle (P0.5) exist.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from core.intel.store import IntelEvent


TRANSITION_METHOD_VERSION = "v0_distress_lifecycle_4state"
PUBLIC_STATUS_RETIRE_AFTER_HOURS = 24


def _status_for_lifecycle(lifecycle: str) -> str:
    from core.domain.live_contracts import IncidentStatus

    return {
        "resolved": IncidentStatus.RESOLVED.value,
        "needs_review": IncidentStatus.NEEDS_REVIEW.value,
        "archived": IncidentStatus.OUTCOME_UNKNOWN.value,
    }.get(str(lifecycle), IncidentStatus.ACTIVE.value)


def public_incident_status(incident: dict, *, now: datetime) -> str:
    """Public real-world status, independent from the Live/Play surface."""
    from core.domain.live_contracts import IncidentStatus
    from core.intel.lifecycle import parse_utc

    raw = incident.get("incident_status")
    if raw not in {status.value for status in IncidentStatus}:
        raw = _status_for_lifecycle(str(incident.get("lifecycle") or "active"))
    if raw != IncidentStatus.ACTIVE.value:
        return raw
    last_update = parse_utc(str(incident.get("last_update_at") or ""))
    if last_update is None:
        return raw
    if (now - last_update).total_seconds() >= PUBLIC_STATUS_RETIRE_AFTER_HOURS * 3600:
        return IncidentStatus.OUTCOME_UNKNOWN.value
    return raw


def _reason_code_for(event: IntelEvent, lifecycle: str) -> str:
    """Best-effort label of which of core.intel.lifecycle.
    distress_lifecycle()'s own signals produced this state -- an honest
    account of what was observed (docs/updates.md P0.5), not a claim of
    full future-taxonomy precision (see module docstring)."""
    from core.intel.lifecycle import latest_own_reply_outcome

    if latest_own_reply_outcome(event) is not None:
        return "self_reply_outcome"
    if lifecycle == "resolved":
        return "cross_post_resolution_signal"
    if lifecycle == "needs_review":
        return "ambiguous_reply"
    if lifecycle == "archived":
        return "silence_after_threshold"
    return "text_classification"


def _record_transition(
    db, *, incident_id: str, from_state: Optional[str], to_state: str,
    event: IntelEvent, reason_code: str, now: datetime,
) -> None:
    from core.db.models import IncidentTransitionDB

    transition_id = f"trans:{incident_id}:{now.isoformat()}"
    db.add(IncidentTransitionDB(
        transition_id=transition_id, incident_id=incident_id,
        from_state=from_state, to_state=to_state, transition_at=now,
        effective_at=event.timestamp_utc, reason_code=reason_code,
        supporting_observation_ids=[event.id], contradicting_observation_ids=[],
        method_version=TRANSITION_METHOD_VERSION,
        review_required=(to_state == "needs_review"),
    ))


def sync_incident_for_event(
    event: IntelEvent, *, lifecycle: str, case_type: Optional[str] = None,
) -> None:
    """Idempotent upsert keyed by event.id. Never raises -- a caller in
    an intel_store subscriber callback already isolates exceptions, but
    this stays defensive on its own too since it may also be called
    directly (e.g. from a backfill script). Every actual lifecycle
    transition is also recorded as its own IncidentTransitionDB row
    (docs/updates.md P0.5) -- append-only, never edited in place."""
    from core.db.models import HumanitarianIncidentDB
    from core.db.session import session_scope

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as db:
        row = db.get(HumanitarianIncidentDB, event.id)
        if row is None:
            # Subscriber fan-out and operator backfills can legitimately race on
            # the same first observation. Use a savepoint so the loser of the
            # insert race can re-read and continue as an idempotent update.
            from sqlalchemy.exc import IntegrityError

            try:
                with db.begin_nested():
                    row = HumanitarianIncidentDB(
                        incident_id=event.id,
                        lifecycle=lifecycle,
                        incident_status=_status_for_lifecycle(lifecycle),
                        case_type=case_type,
                        reported_at=event.timestamp_utc,
                        last_update_at=event.timestamp_utc,
                        state_changed_at=now,
                        resolved_at=now if lifecycle == "resolved" else None,
                        archived_at=now if lifecycle == "archived" else None,
                        source_observation_ids=[event.id],
                        review_status="none",
                        revision=1,
                    )
                    db.add(row)
                    db.flush()
                    _record_transition(
                        db, incident_id=event.id, from_state=None, to_state=lifecycle,
                        event=event, reason_code=_reason_code_for(event, lifecycle), now=now,
                    )
                return
            except IntegrityError:
                row = db.get(HumanitarianIncidentDB, event.id)
                if row is None:
                    raise

        # docs/updates.md P0.6: "out-of-order source updates do not move
        # reported_at forward" -- the same principle applies to
        # last_update_at here: a delayed/out-of-order observation must
        # never make the incident LOOK older than an already-processed
        # later one. reported_at itself is never touched after creation
        # (set once above), satisfying that half of the rule directly.
        from core.intel.lifecycle import parse_utc

        new_ts = parse_utc(event.timestamp_utc)
        current_ts = parse_utc(row.last_update_at) if row.last_update_at else None
        if new_ts is None or current_ts is None or new_ts >= current_ts:
            row.last_update_at = event.timestamp_utc
        row.revision = (row.revision or 1) + 1
        row.incident_status = _status_for_lifecycle(lifecycle)
        if case_type and not row.case_type:
            row.case_type = case_type
        if row.lifecycle != lifecycle:
            previous_lifecycle = row.lifecycle
            row.lifecycle = lifecycle
            row.state_changed_at = now
            if lifecycle == "resolved" and row.resolved_at is None:
                row.resolved_at = now
            if lifecycle == "archived" and row.archived_at is None:
                row.archived_at = now
            _record_transition(
                db, incident_id=event.id, from_state=previous_lifecycle, to_state=lifecycle,
                event=event, reason_code=_reason_code_for(event, lifecycle), now=now,
            )


def get_incident(incident_id: str):
    from core.db.models import HumanitarianIncidentDB
    from core.db.session import session_scope

    with session_scope() as db:
        row = db.get(HumanitarianIncidentDB, incident_id)
        if row is None:
            return None
        return {
            "incident_id": row.incident_id,
            "lifecycle": row.lifecycle,
            "incident_status": row.incident_status or _status_for_lifecycle(row.lifecycle),
            "case_type": row.case_type,
            "reported_at": row.reported_at,
            "last_update_at": row.last_update_at,
            "state_changed_at": row.state_changed_at.isoformat() if row.state_changed_at else None,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "source_observation_ids": list(row.source_observation_ids or []),
            "review_status": row.review_status,
            "revision": row.revision,
            "current_drift_id": row.current_drift_id,
        }


def resolve_public_incident_state(event: IntelEvent, *, now: datetime, same_source: list) -> dict:
    """docs/updates.md P0.10: Live authority cutover.

    The single function core.live.feed.public_signal_collection and
    core.live_edge_publisher.public_event_from_row must both call for a
    Humanitarian marker's lifecycle/timestamps, instead of each calling
    core.intel.lifecycle.distress_lifecycle() directly at read time.
    When a canonical HumanitarianIncidentDB row exists (every event
    classified humanitarian, since core.intel.humanitarian_incident.
    register() -- P0.3/P0.9), its precomputed, write-time state IS the
    public authority: lifecycle/reported_at/last_update_at/
    state_changed_at/resolved_at all come from the incident, not from
    re-deriving them from the event's own text/metadata on every request.

    Falls back to the pre-P0.10 read-time recomputation ONLY for an
    event with no canonical incident -- e.g. a Maritime Safety marker
    (docs/updates.md P0.8: a beacon/nav-status event never gets a
    HumanitarianIncidentDB row at all) or a genuinely pre-P0.3 legacy
    record. This fallback is deliberate, not a loophole: those events
    were never meant to have canonical incident state in the first
    place, so there is nothing stale to prefer over a live computation.

    Known, accepted consequence of the cutover (not a bug): the
    canonical incident is updated asynchronously, off-thread, by
    intel_store's subscriber fan-out (P0.3/P0.9) -- a read landing in
    the brief window between a new update and that background sync
    completing sees the incident's still-slightly-stale state rather
    than an instantaneous recomputation. The same trade-off already
    applies to every other staged-shadow authority this codebase has
    cut over (P0.5 lifecycle, P0.7 Drift ownership).
    """
    incident = get_incident(event.id)
    if incident is not None:
        return {
            "lifecycle": incident["lifecycle"],
            "incident_status": public_incident_status(incident, now=now),
            "reported_at": incident["reported_at"],
            "last_update_at": incident["last_update_at"],
            "state_changed_at": incident["state_changed_at"],
            "resolved_at": incident["resolved_at"],
        }

    from core.intel.lifecycle import distress_lifecycle

    fallback_lifecycle = distress_lifecycle(event, now=now, same_source=same_source)
    return {
        "lifecycle": fallback_lifecycle,
        "incident_status": _status_for_lifecycle(fallback_lifecycle),
        "reported_at": event.timestamp_utc,
        "last_update_at": event.timestamp_utc,
        "state_changed_at": None,
        "resolved_at": None,
    }


def list_transitions(incident_id: str) -> list[dict]:
    """Every recorded transition for one incident, oldest first --
    docs/updates.md P0.5's audit trail. Never edited in place; a caller
    wanting the current lifecycle should still read get_incident()."""
    from core.db.models import IncidentTransitionDB
    from core.db.session import session_scope

    with session_scope() as db:
        rows = (
            db.query(IncidentTransitionDB)
            .filter(IncidentTransitionDB.incident_id == incident_id)
            .order_by(IncidentTransitionDB.transition_at.asc())
            .all()
        )
        return [
            {
                "transition_id": r.transition_id,
                "from_state": r.from_state,
                "to_state": r.to_state,
                "transition_at": r.transition_at.isoformat() if r.transition_at else None,
                "reason_code": r.reason_code,
                "supporting_observation_ids": list(r.supporting_observation_ids or []),
                "contradicting_observation_ids": list(r.contradicting_observation_ids or []),
                "method_version": r.method_version,
                "review_required": r.review_required,
            }
            for r in rows
        ]


def _on_intel_event(event: IntelEvent) -> None:
    """core.intel.store.intel_store subscriber: syncs the canonical
    incident for a Humanitarian-service event on every store write.
    Never raises -- the subscriber fan-out already isolates exceptions
    per-callback, but this stays defensive on its own too."""
    try:
        from core.intel.lifecycle import distress_lifecycle
        from core.intel.service_taxonomy import classify_service
        from core.intel.store import intel_store

        if classify_service(event).service != "humanitarian":
            return
        same_source = [
            other for other in intel_store.events(limit=200)
            if other.source == event.source and other.id != event.id
        ]
        lifecycle = distress_lifecycle(event, now=datetime.now(timezone.utc), same_source=same_source)
        case_type = event.metadata.get("humanitarian_case_type") or event.metadata.get("case_type")
        sync_incident_for_event(event, lifecycle=lifecycle, case_type=case_type)

        from core.intel.claims import record_claims_for_incident, sync_assessments_for_incident
        from core.intel.humanitarian_recognition import assess

        assessment = assess(event.text or event.title)
        record_claims_for_incident(event.id, event, assessment)
        sync_assessments_for_incident(event.id)

        from core.intel.correlation import generate_correlation_decisions

        generate_correlation_decisions(event, lifecycle=lifecycle)
    except Exception:  # pragma: no cover - never break ingestion over incident sync
        pass


def register() -> None:
    """Subscribe the incident-sync callback onto intel_store's existing
    fan-out hook -- call once at startup (core.bootstrap), the same
    pattern core.intel.fusion.register() already uses."""
    from core.intel.store import intel_store

    intel_store.subscribe(_on_intel_event)
