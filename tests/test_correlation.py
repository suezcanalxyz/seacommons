# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P2.1: CorrelationDecision.

Exit gate (v0-bounded, per module docstring): every decision this
module produces is a candidate pairing for review, never an automatic
merge -- a temporal-only match is always UNCERTAIN, never SAME_INCIDENT,
and no HumanitarianIncidentDB row is ever mutated by this module.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.intel.correlation import (
    DECISION_NEW_INCIDENT,
    DECISION_UNCERTAIN,
    NOT_YET_COMPUTABLE,
    generate_correlation_decisions,
    get_correlation_decisions,
)
from core.intel.humanitarian_incident import sync_incident_for_event
from core.intel.store import IntelEvent


@pytest.fixture(autouse=True)
def _fresh_tables():
    from core.db.models import CorrelationDecisionDB, HumanitarianIncidentDB
    from core.db.session import engine, session_scope

    HumanitarianIncidentDB.__table__.create(bind=engine(), checkfirst=True)
    CorrelationDecisionDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(HumanitarianIncidentDB).delete()
        db.query(CorrelationDecisionDB).delete()
    yield


def _event(event_id, timestamp, source="Alarm Phone"):
    return IntelEvent(
        id=event_id, type="distress", text=f"distress {event_id}", title=f"distress {event_id}",
        source=source, timestamp_utc=timestamp, metadata={"is_distress": True},
    )


def test_no_open_incidents_nearby_yields_new_incident():
    now = datetime.now(timezone.utc)
    event = _event(f"c1-{uuid.uuid4()}", now.isoformat())
    decisions = generate_correlation_decisions(event, lifecycle="active")
    assert len(decisions) == 1
    assert decisions[0].decision == DECISION_NEW_INCIDENT
    assert decisions[0].candidate_incident_id is None


def test_a_temporally_close_open_incident_is_uncertain_never_same_incident():
    """docs/updates.md P2.1: "Model similarity cannot be sole merge
    evidence" -- temporal proximity alone must never produce
    SAME_INCIDENT."""
    now = datetime.now(timezone.utc)
    existing = _event(f"c2-existing-{uuid.uuid4()}", now.isoformat())
    sync_incident_for_event(existing, lifecycle="active")

    new_event = _event(f"c2-new-{uuid.uuid4()}", (now + timedelta(hours=1)).isoformat())
    decisions = generate_correlation_decisions(new_event, lifecycle="active")

    assert len(decisions) == 1
    assert decisions[0].decision == DECISION_UNCERTAIN
    assert decisions[0].candidate_incident_id == existing.id
    assert "temporal_proximity" in decisions[0].supporting_features
    assert decisions[0].review_state == "pending_review"


def test_a_temporally_distant_incident_is_not_a_candidate():
    now = datetime.now(timezone.utc)
    existing = _event(f"c3-existing-{uuid.uuid4()}", now.isoformat())
    sync_incident_for_event(existing, lifecycle="active")

    far_event = _event(f"c3-far-{uuid.uuid4()}", (now + timedelta(hours=48)).isoformat())
    decisions = generate_correlation_decisions(far_event, lifecycle="active")

    assert len(decisions) == 1
    assert decisions[0].decision == DECISION_NEW_INCIDENT


def test_a_resolved_incident_is_not_a_candidate():
    now = datetime.now(timezone.utc)
    existing = _event(f"c4-existing-{uuid.uuid4()}", now.isoformat())
    sync_incident_for_event(existing, lifecycle="resolved")

    new_event = _event(f"c4-new-{uuid.uuid4()}", (now + timedelta(hours=1)).isoformat())
    decisions = generate_correlation_decisions(new_event, lifecycle="active")

    assert len(decisions) == 1
    assert decisions[0].decision == DECISION_NEW_INCIDENT


def test_no_correlation_decision_ever_mutates_the_candidate_incident():
    from core.intel.humanitarian_incident import get_incident

    now = datetime.now(timezone.utc)
    existing = _event(f"c5-existing-{uuid.uuid4()}", now.isoformat())
    sync_incident_for_event(existing, lifecycle="active")
    before = get_incident(existing.id)

    new_event = _event(f"c5-new-{uuid.uuid4()}", (now + timedelta(hours=1)).isoformat())
    generate_correlation_decisions(new_event, lifecycle="active")

    after = get_incident(existing.id)
    assert before == after


def test_get_correlation_decisions_returns_persisted_rows():
    now = datetime.now(timezone.utc)
    event = _event(f"c6-{uuid.uuid4()}", now.isoformat())
    generate_correlation_decisions(event, lifecycle="active")
    fetched = get_correlation_decisions(event.id)
    assert len(fetched) == 1
    assert fetched[0].observation_id == event.id


def test_not_yet_computable_signals_are_named():
    assert "spatial_overlap" in NOT_YET_COMPUTABLE
    assert "exact_thread_source_id_match" in NOT_YET_COMPUTABLE


def test_wired_into_the_live_intel_store_entry_point():
    """The real entry point: intel_store.add() -> _on_intel_event ->
    generate_correlation_decisions, not just the standalone function."""
    from core.intel.humanitarian_incident import register
    from core.intel.store import intel_store

    register()  # idempotent: subscribe() may already have this callback from bootstrap/other tests

    now = datetime.now(timezone.utc)
    existing = _event(f"c7-existing-{uuid.uuid4()}", now.isoformat())
    intel_store.add(existing)

    new_event = _event(f"c7-new-{uuid.uuid4()}", (now + timedelta(hours=1)).isoformat())
    intel_store.add(new_event)

    import time
    for _ in range(50):
        decisions = get_correlation_decisions(new_event.id)
        if decisions:
            break
        time.sleep(0.05)

    assert decisions
    assert decisions[0].decision in (DECISION_UNCERTAIN, DECISION_NEW_INCIDENT)


def test_correlation_decisions_route_exposes_the_real_decisions() -> None:
    from fastapi.testclient import TestClient

    from core.api.main import app

    now = datetime.now(timezone.utc)
    event = _event(f"c8-{uuid.uuid4()}", now.isoformat())
    generate_correlation_decisions(event, lifecycle="active")

    response = TestClient(app).get(f"/api/v1/audit/correlation-decisions/{event.id}")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["decisions"]) == 1
    assert "spatial_overlap" in payload["not_yet_computable_signals"]
