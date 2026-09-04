# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P0.3: canonical HumanitarianIncident.

Exit gate (v0-bounded, documented in the module itself): persisted
state_changed_at/resolved_at/archived_at exist and update correctly on
real lifecycle transitions -- full cross-source correlation is P2.1, a
later packet.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import pytest

from core.intel.humanitarian_incident import (
    _on_intel_event,
    get_incident,
    register,
    sync_incident_for_event,
)
from core.intel.store import IntelEvent, intel_store


@pytest.fixture(autouse=True)
def _fresh_table():
    from core.db.models import HumanitarianIncidentDB
    from core.db.session import engine, session_scope

    HumanitarianIncidentDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(HumanitarianIncidentDB).delete()
    yield


def _distress_event(event_id, text, *, timestamp=None):
    return IntelEvent(
        id=event_id, type="distress", severity="high", lat=35.5, lon=14.1,
        title=text[:80], text=text, source="Alarm Phone",
        timestamp_utc=timestamp or datetime.now(timezone.utc).isoformat(),
        metadata={"is_distress": True},
    )


def test_a_new_incident_is_created_on_first_sync():
    event = _distress_event("h1", "MAYDAY 30 people taking water off Libya")
    sync_incident_for_event(event, lifecycle="active")

    incident = get_incident("h1")
    assert incident is not None
    assert incident["lifecycle"] == "active"
    assert incident["revision"] == 1
    assert incident["resolved_at"] is None
    assert incident["source_observation_ids"] == ["h1"]


def test_state_changed_at_updates_only_when_lifecycle_actually_changes():
    event = _distress_event("h2", "MAYDAY people in the water")
    sync_incident_for_event(event, lifecycle="active")
    first = get_incident("h2")

    time.sleep(0.01)
    sync_incident_for_event(event, lifecycle="active")  # same lifecycle -- no-op
    second = get_incident("h2")
    assert second["state_changed_at"] == first["state_changed_at"]
    assert second["revision"] == 2  # last_update_at/revision still advance

    sync_incident_for_event(event, lifecycle="resolved")  # real transition
    third = get_incident("h2")
    assert third["state_changed_at"] != first["state_changed_at"]


def test_resolved_at_is_set_once_and_never_cleared():
    event = _distress_event("h3", "distress")
    sync_incident_for_event(event, lifecycle="active")
    sync_incident_for_event(event, lifecycle="resolved")
    first_resolved_at = get_incident("h3")["resolved_at"]
    assert first_resolved_at is not None

    time.sleep(0.01)
    sync_incident_for_event(event, lifecycle="resolved")  # repeated resolved sync
    assert get_incident("h3")["resolved_at"] == first_resolved_at


def test_archived_at_is_set_when_lifecycle_becomes_archived():
    event = _distress_event("h4", "distress")
    sync_incident_for_event(event, lifecycle="active")
    sync_incident_for_event(event, lifecycle="archived")
    incident = get_incident("h4")
    assert incident["archived_at"] is not None
    assert incident["lifecycle"] == "archived"


def test_case_type_is_recorded_once_available_and_not_overwritten_with_none():
    event = _distress_event("h5", "distress")
    sync_incident_for_event(event, lifecycle="active", case_type="distress")
    sync_incident_for_event(event, lifecycle="active", case_type=None)
    assert get_incident("h5")["case_type"] == "distress"


def test_get_incident_returns_none_for_an_unknown_id():
    assert get_incident("does-not-exist") is None


# ── subscriber wiring ────────────────────────────────────────────────────


def test_on_intel_event_skips_non_humanitarian_events():
    event = IntelEvent(
        id="ais1", type="ais_anomaly", severity="medium", lat=35.5, lon=14.1,
        source="mda", metadata={"anomaly_type": "gap", "maritime_domain": "grey_zone"},
    )
    _on_intel_event(event)  # must not raise
    assert get_incident("ais1") is None


def test_on_intel_event_syncs_a_real_humanitarian_event():
    event = _distress_event("h6", "MAYDAY urgent rescue needed")
    _on_intel_event(event)
    incident = get_incident("h6")
    assert incident is not None
    assert incident["lifecycle"] == "active"


def test_registered_subscriber_syncs_on_a_real_intel_store_add():
    """docs/updates.md P0.3: end-to-end through the real intel_store.add()
    write path and the real (async, background-thread) subscriber
    fan-out -- not a direct function call."""
    with intel_store._lock:
        intel_store._subscribers.clear()
    register()

    event_id = f"h-e2e-{uuid.uuid4()}"
    event = _distress_event(event_id, "MAYDAY 12 people aboard, taking water")
    intel_store.add(event, dedup_key=event_id)

    incident = None
    for _ in range(50):
        incident = get_incident(event_id)
        if incident is not None:
            break
        time.sleep(0.05)
    assert incident is not None
    assert incident["lifecycle"] == "active"
