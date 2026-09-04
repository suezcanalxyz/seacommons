# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P0.7: Drift ownership and supersession.

Exit gate (v0-bounded, scoped to the ownership pointer only -- see module
docstring): exactly zero or one current_drift_id per incident, and a
resolved/archived incident's Drift is cleared, never operational.
"""
from __future__ import annotations

import pytest

from core.intel.drift_ownership import (
    get_current_drift_id,
    sync_current_drift_for_incident,
)
from core.intel.humanitarian_incident import sync_incident_for_event
from core.intel.store import IntelEvent


@pytest.fixture(autouse=True)
def _fresh_table():
    from core.db.models import HumanitarianIncidentDB
    from core.db.session import engine, session_scope

    HumanitarianIncidentDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(HumanitarianIncidentDB).delete()
    yield


def _make_incident(incident_id, lifecycle="active"):
    event = IntelEvent(id=incident_id, type="distress", text="distress", title="distress",
                        source="Alarm Phone", timestamp_utc="2026-09-04T08:00:00+00:00")
    sync_incident_for_event(event, lifecycle=lifecycle)


def test_setting_a_current_drift_id_on_an_active_incident():
    _make_incident("d1", lifecycle="active")
    result = sync_current_drift_for_incident("d1", "drift-abc")
    assert result == "drift-abc"
    assert get_current_drift_id("d1") == "drift-abc"


def test_a_new_position_supersedes_the_old_current_drift():
    """docs/updates.md P0.7: "new accepted position -> old Drift
    superseded before new current Drift becomes public" -- a single
    pointer, so there is never a window with two."""
    _make_incident("d2", lifecycle="active")
    sync_current_drift_for_incident("d2", "drift-old")
    assert get_current_drift_id("d2") == "drift-old"

    result = sync_current_drift_for_incident("d2", "drift-new")
    assert result == "drift-new"
    assert get_current_drift_id("d2") == "drift-new"  # old one is simply gone, never both


def test_a_resolved_incident_never_gets_a_current_drift():
    _make_incident("d3", lifecycle="resolved")
    result = sync_current_drift_for_incident("d3", "drift-x")
    assert result is None
    assert get_current_drift_id("d3") is None


def test_an_archived_incident_never_gets_a_current_drift():
    _make_incident("d4", lifecycle="archived")
    result = sync_current_drift_for_incident("d4", "drift-x")
    assert result is None
    assert get_current_drift_id("d4") is None


def test_resolving_an_incident_clears_its_existing_current_drift():
    """docs/updates.md P0.7: "RESOLVED -> remove/freeze from Live
    immediately" -- an incident that already had an operational Drift
    loses it the moment it resolves."""
    event = IntelEvent(id="d5", type="distress", text="distress", title="distress",
                        source="Alarm Phone", timestamp_utc="2026-09-04T08:00:00+00:00")
    sync_incident_for_event(event, lifecycle="active")
    sync_current_drift_for_incident("d5", "drift-active")
    assert get_current_drift_id("d5") == "drift-active"

    resolved_event = IntelEvent(id="d5", type="distress", text="rescued, all safe",
                                 title="resolved", source="Alarm Phone",
                                 timestamp_utc="2026-09-04T09:00:00+00:00")
    sync_incident_for_event(resolved_event, lifecycle="resolved")
    sync_current_drift_for_incident("d5", "drift-active")  # next sync cycle re-evaluates

    assert get_current_drift_id("d5") is None


def test_sync_returns_none_for_an_unknown_incident():
    assert sync_current_drift_for_incident("does-not-exist", "drift-x") is None


def test_get_current_drift_id_returns_none_for_an_unknown_incident():
    assert get_current_drift_id("does-not-exist") is None


def test_outcome_unknown_status_never_gets_operational_drift_even_if_legacy_lifecycle_is_active():
    from core.db.models import HumanitarianIncidentDB
    from core.db.session import session_scope

    _make_incident("d6", lifecycle="active")
    with session_scope() as db:
        row = db.get(HumanitarianIncidentDB, "d6")
        row.incident_status = "outcome_unknown"
        row.lifecycle = "active"  # deliberately inconsistent legacy row

    result = sync_current_drift_for_incident("d6", "drift-x")
    assert result is None
    assert get_current_drift_id("d6") is None
