from __future__ import annotations

from datetime import datetime, timezone

import pytest
from core.intel.humanitarian_incident import (
    _on_intel_event,
    get_incident,
    sync_incident_for_event,
)
from core.intel.store import IntelEvent


@pytest.fixture(autouse=True)
def _tables():
    from core.db.models import (
        AssessmentDB,
        ClaimDB,
        CorrelationDecisionDB,
        HumanitarianIncidentDB,
        IntelEventDB,
    )
    from core.db.session import engine, session_scope

    for table in (
        IntelEventDB.__table__, HumanitarianIncidentDB.__table__, ClaimDB.__table__,
        CorrelationDecisionDB.__table__, AssessmentDB.__table__,
    ):
        table.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(AssessmentDB).delete()
        db.query(CorrelationDecisionDB).delete()
        db.query(ClaimDB).delete()
        db.query(HumanitarianIncidentDB).delete()
        db.query(IntelEventDB).delete()
    yield


def _seed_origin(incident_id="origin-1"):
    from core.db.models import ClaimDB, IntelEventDB
    from core.db.session import session_scope

    ts = datetime.now(timezone.utc).isoformat()
    origin = IntelEvent(
        id=incident_id, type="distress", severity="high", lat=35.0, lon=15.0,
        title="MAYDAY 42 people aboard", text="42 people aboard Ocean Viking responding",
        source="Alarm Phone", timestamp_utc=ts,
        metadata={"is_distress": True, "responder_assets": ["Ocean Viking"], "platform": "x"},
    )
    sync_incident_for_event(origin, lifecycle="active")
    with session_scope() as db:
        db.add(IntelEventDB(
            id=origin.id, timestamp_utc=ts, type=origin.type, severity=origin.severity,
            lat=origin.lat, lon=origin.lon, title=origin.title, text=origin.text,
            source=origin.source, linked_mmsi="", meta=origin.metadata,
        ))
        db.add(ClaimDB(
            claim_id=f"claim:{incident_id}:people", incident_id=incident_id,
            claim_type="people_aboard", value={"count": 42}, observation_id=origin.id,
            source_id=origin.source, claimed_at=ts, observed_at=ts,
            extraction_method="test", verification_status="unverified",
        ))
    return origin


def _verification_event(event_id="verify-1"):
    return IntelEvent(
        id=event_id, type="distress", severity="high", lat=35.05, lon=15.02,
        title="Ocean Viking rescued 42 people", text="Ocean Viking rescued 42 people from a boat in distress.",
        source="SOS Méditerranée", timestamp_utc=datetime.now(timezone.utc).isoformat(),
        metadata={"is_distress": True, "service": "humanitarian", "lane": "resolution", "transport": "rss"},
    )


def test_verification_event_enriches_existing_incident_without_opening_another():
    from core.intel.humanitarian_verification import process_verification_event

    origin = _seed_origin()
    event = _verification_event()
    result = process_verification_event(event)

    assert get_incident(event.id) is None
    assert result["associated_incident_ids"] == [origin.id]
    assert result["resolution_assessments"][0]["value"]["outcome"] == "rescue_confirmed"


def test_verification_event_replay_is_idempotent_for_claims_and_resolution():
    from core.db.models import AssessmentDB, ClaimDB
    from core.db.session import session_scope
    from core.intel.humanitarian_verification import process_verification_event

    _seed_origin("origin-replay")
    event = _verification_event("verify-replay")
    first = process_verification_event(event)
    second = process_verification_event(event)
    assert first["associated_incident_ids"] == second["associated_incident_ids"]

    with session_scope() as db:
        assert db.query(ClaimDB).filter_by(incident_id="origin-replay").count() == 3
        assert db.query(AssessmentDB).filter_by(incident_id="origin-replay", field_type="resolution").count() == 1


def test_subscriber_routes_verification_source_to_enrichment_not_incident_creation():
    from core.intel.humanitarian_verification import get_verification_summary

    origin = _seed_origin("origin-subscriber")
    event = _verification_event("verify-subscriber")
    _on_intel_event(event)

    assert get_incident(event.id) is None
    summary = get_verification_summary(origin.id)
    assert summary["resolution"]["value"]["outcome"] == "rescue_confirmed"


def test_subscriber_accepts_real_x_verification_handle_without_distress_service_tag():
    from core.intel.humanitarian_verification import get_verification_summary

    origin = _seed_origin("origin-real-x-handle")
    event = _verification_event("verify-real-x-handle")
    event.type = "twitter"
    event.source = "SOSMedIntl"
    event.metadata = {"platform": "x", "transport": "x"}
    _on_intel_event(event)

    assert get_incident(event.id) is None
    summary = get_verification_summary(origin.id)
    assert summary["resolution"]["value"]["outcome"] == "rescue_confirmed"


def test_verification_source_without_claims_does_not_create_association_noise():
    from core.db.models import CorrelationDecisionDB
    from core.db.session import session_scope
    from core.intel.humanitarian_verification import process_verification_event

    _seed_origin("origin-noise")
    event = IntelEvent(
        id="verify-noise", type="twitter", severity="low",
        title="Our annual report is online", text="Read our annual report and latest organisation news.",
        source="SOSMedIntl", timestamp_utc=datetime.now(timezone.utc).isoformat(),
        metadata={"platform": "x", "transport": "x"},
    )
    result = process_verification_event(event)

    assert result["processed"] is False
    assert result["reason"] == "no_verification_claims"
    with session_scope() as db:
        assert db.query(CorrelationDecisionDB).filter_by(observation_id=event.id).count() == 0


def test_operator_summary_excludes_internal_vessel_identifiers():
    from core.intel.humanitarian_verification import get_verification_summary

    origin = _seed_origin("origin-safe")
    process_event = _verification_event("verify-safe")
    from core.intel.humanitarian_verification import process_verification_event
    process_verification_event(process_event)

    summary = get_verification_summary(origin.id)
    rendered = repr(summary).lower()
    assert "258479000" not in rendered
    assert "mmsi" not in rendered
    assert "imo" not in rendered
    assert "callsign" not in rendered


def test_audit_verification_route_is_operator_safe():
    from core.api.main import app
    from fastapi.testclient import TestClient

    origin = _seed_origin("origin-audit-safe")
    _on_intel_event(_verification_event("verify-audit-safe"))
    response = TestClient(app).get(f"/api/v1/audit/humanitarian-verification/{origin.id}")
    assert response.status_code == 200
    rendered = response.text.lower()
    assert "mmsi" not in rendered
    assert "imo" not in rendered
    assert "callsign" not in rendered
    assert "tracker" not in rendered
    assert "rescue_confirmed" in rendered
