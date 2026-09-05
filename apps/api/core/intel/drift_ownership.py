# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drift ownership and supersession (docs/updates.md P0.7).

**Goal:** a Drift is a versioned derived artifact owned by an incident --
"exactly zero or one operational current Drift per incident."

v0 scope, honestly bounded: this module tracks ownership as one nullable
``HumanitarianIncidentDB.current_drift_id`` pointer -- a single column
makes "zero or one current" true by construction, not by a convention
callers must remember. It does NOT yet change how
``core.live.feed.public_drift_collection()`` selects what is publicly
visible; that function still rediscovers arbitrary completed
``DriftResultDB`` rows (docs/updates.md P0.7's own named anti-pattern:
"public_drift_collection() must select incident.current_drift_id; it
must not rediscover arbitrary completed jobs"). Swapping that live
selection is a later, deliberately separate packet once this ownership
signal has been proven correct in parallel -- the same staged pattern
P0.3 already used for incident lifecycle.

Enforces two of P0.7's rules directly, since they only touch this
pointer, not the live read path:
  - "new accepted position -> old Drift superseded before new current
    Drift becomes public": a single pointer can only ever name one
    drift_id, so setting a new one always supersedes the old one, with
    no window where two could both read as current.
  - "RESOLVED -> remove/freeze from Live immediately" / "ARCHIVED ->
    never operational": clears the pointer outright once the owning
    incident's lifecycle reaches either state.
"""
from __future__ import annotations

from typing import Optional

_TERMINAL_LIFECYCLES = frozenset({"resolved", "archived"})
_TERMINAL_INCIDENT_STATUSES = frozenset({"resolved", "outcome_unknown"})


def sync_current_drift_for_incident(
    incident_id: str, candidate_drift_id: Optional[str],
) -> Optional[str]:
    """Set (or clear) the incident's current_drift_id, enforcing the
    terminal-lifecycle rule. Returns the resulting current_drift_id
    (None if cleared or the incident does not exist). Idempotent: called
    again with the same candidate on an unchanged incident is a no-op.
    """
    from core.db.models import HumanitarianIncidentDB
    from core.db.session import session_scope

    with session_scope() as db:
        row = db.get(HumanitarianIncidentDB, incident_id)
        if row is None:
            return None
        if (
            row.lifecycle in _TERMINAL_LIFECYCLES
            or (row.incident_status or "") in _TERMINAL_INCIDENT_STATUSES
        ):
            row.current_drift_id = None
            return None
        row.current_drift_id = candidate_drift_id
        return candidate_drift_id


def get_current_drift_id(incident_id: str) -> Optional[str]:
    from core.db.models import HumanitarianIncidentDB
    from core.db.session import session_scope

    with session_scope() as db:
        row = db.get(HumanitarianIncidentDB, incident_id)
        return row.current_drift_id if row is not None else None
