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


def sync_incident_for_event(
    event: IntelEvent, *, lifecycle: str, case_type: Optional[str] = None,
) -> None:
    """Idempotent upsert keyed by event.id. Never raises -- a caller in
    an intel_store subscriber callback already isolates exceptions, but
    this stays defensive on its own too since it may also be called
    directly (e.g. from a backfill script)."""
    from core.db.models import HumanitarianIncidentDB
    from core.db.session import session_scope

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as db:
        row = db.get(HumanitarianIncidentDB, event.id)
        if row is None:
            db.add(HumanitarianIncidentDB(
                incident_id=event.id,
                lifecycle=lifecycle,
                case_type=case_type,
                reported_at=event.timestamp_utc,
                last_update_at=event.timestamp_utc,
                state_changed_at=now,
                resolved_at=now if lifecycle == "resolved" else None,
                archived_at=now if lifecycle == "archived" else None,
                source_observation_ids=[event.id],
                review_status="none",
                revision=1,
            ))
            return

        row.last_update_at = event.timestamp_utc
        row.revision = (row.revision or 1) + 1
        if case_type and not row.case_type:
            row.case_type = case_type
        if row.lifecycle != lifecycle:
            row.lifecycle = lifecycle
            row.state_changed_at = now
            if lifecycle == "resolved" and row.resolved_at is None:
                row.resolved_at = now
            if lifecycle == "archived" and row.archived_at is None:
                row.archived_at = now


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
            "case_type": row.case_type,
            "reported_at": row.reported_at,
            "last_update_at": row.last_update_at,
            "state_changed_at": row.state_changed_at.isoformat() if row.state_changed_at else None,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "source_observation_ids": list(row.source_observation_ids or []),
            "review_status": row.review_status,
            "revision": row.revision,
        }


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
    except Exception:  # pragma: no cover - never break ingestion over incident sync
        pass


def register() -> None:
    """Subscribe the incident-sync callback onto intel_store's existing
    fan-out hook -- call once at startup (core.bootstrap), the same
    pattern core.intel.fusion.register() already uses."""
    from core.intel.store import intel_store

    intel_store.subscribe(_on_intel_event)
