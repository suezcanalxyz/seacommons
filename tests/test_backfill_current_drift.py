# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P0.11: backfill HumanitarianIncident.current_drift_id
for incidents whose drift completed before core.intel.drift_service
started syncing it going forward. Same dry-run-first, auditable pattern
as core.intel.backfill_drift_maintenance."""
from __future__ import annotations

import uuid

import pytest

from core.intel.backfill_current_drift import find_candidates, run
from core.intel.drift_ownership import get_current_drift_id
from core.intel.humanitarian_incident import sync_incident_for_event
from core.intel.store import IntelEvent, intel_store


@pytest.fixture(autouse=True)
def _fresh_tables():
    from core.db.models import HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import engine, session_scope

    HumanitarianIncidentDB.__table__.create(bind=engine(), checkfirst=True)
    IncidentTransitionDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(HumanitarianIncidentDB).delete()
        db.query(IncidentTransitionDB).delete()
    yield


def _open_incident_with_completed_drift(*, drift_job_id="job-1", lifecycle="active"):
    event_id = f"backfill-{uuid.uuid4()}"
    # Unique text per call: intel_store.add()'s dedup keys off
    # source+title+text[:120] against a shared, process-global singleton --
    # a fixed string reused across calls in this same test file silently
    # drops every call after the first, so IntelEventDB never gets a row
    # for it and find_candidates() (which reads IntelEventDB directly)
    # would wrongly see no candidate.
    text = f"MAYDAY backfill test [{event_id}]"
    event = IntelEvent(
        id=event_id, type="distress", severity="high", lat=35.5, lon=14.1,
        title=text[:80], text=text, source="Alarm Phone",
        timestamp_utc="2026-09-04T08:00:00+00:00",
        metadata={
            "is_distress": True, "drift_job_id": drift_job_id, "drift_status": "completed",
        },
    )
    intel_store.add(event)
    sync_incident_for_event(event, lifecycle=lifecycle)
    return event_id


def test_an_open_incident_with_a_completed_drift_and_no_pointer_is_a_candidate():
    event_id = _open_incident_with_completed_drift()
    candidates = find_candidates()
    match = next(c for c in candidates if c.incident_id == event_id)
    assert match.drift_job_id == "job-1"


def test_an_incident_with_no_completed_drift_is_not_a_candidate():
    event_id = f"backfill-nodrift-{uuid.uuid4()}"
    text = f"MAYDAY no drift test [{event_id}]"
    event = IntelEvent(
        id=event_id, type="distress", severity="high", lat=35.5, lon=14.1,
        title=text[:80], text=text, source="Alarm Phone",
        timestamp_utc="2026-09-04T08:00:00+00:00", metadata={"is_distress": True},
    )
    intel_store.add(event)
    sync_incident_for_event(event, lifecycle="active")

    candidates = find_candidates()
    assert not any(c.incident_id == event_id for c in candidates)


def test_a_resolved_incident_is_never_a_candidate():
    event_id = _open_incident_with_completed_drift(lifecycle="resolved")
    candidates = find_candidates()
    assert not any(c.incident_id == event_id for c in candidates)


def test_an_incident_already_holding_a_current_drift_id_is_not_a_candidate():
    from core.intel.drift_ownership import sync_current_drift_for_incident

    event_id = _open_incident_with_completed_drift()
    sync_current_drift_for_incident(event_id, "already-set")

    candidates = find_candidates()
    assert not any(c.incident_id == event_id for c in candidates)


def test_dry_run_never_writes():
    event_id = _open_incident_with_completed_drift()
    report = run(apply=False)
    assert report["scanned"] >= 1
    assert report["backfilled"] == 0
    assert get_current_drift_id(event_id) is None


def test_apply_writes_the_pointer():
    event_id = _open_incident_with_completed_drift(drift_job_id="job-apply")
    report = run(apply=True)
    assert report["backfilled"] >= 1
    assert get_current_drift_id(event_id) == "job-apply"
