from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from core.intel.humanitarian_claims import extract_humanitarian_claims
from core.intel.humanitarian_incident import get_incident, sync_incident_for_event
from core.intel.source_identity import resolve_source_identity
from core.intel.store import IntelEvent


@pytest.fixture(autouse=True)
def _fresh_tables():
    from core.db.models import (
        ClaimDB,
        CorrelationDecisionDB,
        HumanitarianIncidentDB,
        IntelEventDB,
    )
    from core.db.session import engine, session_scope

    for model in (HumanitarianIncidentDB, CorrelationDecisionDB, ClaimDB, IntelEventDB):
        model.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(CorrelationDecisionDB).delete()
        db.query(ClaimDB).delete()
        db.query(HumanitarianIncidentDB).delete()
    yield


def _seed_origin(now: datetime, *, people: int = 42, asset: str = "Ocean Viking") -> IntelEvent:
    from core.db.models import ClaimDB, IntelEventDB
    from core.db.session import session_scope

    event = IntelEvent(
        id=f"origin-{uuid.uuid4()}", type="distress", severity="high", lat=35.5, lon=14.1,
        title=f"{people} people in distress", text=f"{people} people in distress",
        source="Alarm Phone", timestamp_utc=now.isoformat(),
        metadata={"is_distress": True, "platform": "x", "responder_assets": [asset]},
    )
    sync_incident_for_event(event, lifecycle="active")
    with session_scope() as db:
        db.add(IntelEventDB(
            id=event.id, timestamp_utc=event.timestamp_utc, type=event.type,
            severity=event.severity, lat=event.lat, lon=event.lon, title=event.title,
            text=event.text, source=event.source, meta=event.metadata,
        ))
        db.add(ClaimDB(
            claim_id=f"seed:{uuid.uuid4()}", incident_id=event.id, claim_type="people_aboard",
            value={"count": people}, observation_id=event.id, source_id=event.source,
            claimed_at=event.timestamp_utc, observed_at=event.timestamp_utc,
            extraction_method="seed", verification_status="unverified",
        ))
    return event


def _verification_event(now: datetime, *, people: int = 42, lat: float = 35.51, lon: float = 14.11) -> IntelEvent:
    text = f"Ocean Viking rescued {people} people from a boat in distress."
    return IntelEvent(
        id=f"verify-{uuid.uuid4()}", type="news", severity="high", lat=lat, lon=lon,
        title=text, text=text, source="SOS Méditerranée",
        timestamp_utc=(now + timedelta(minutes=30)).isoformat(),
        metadata={"service": "humanitarian", "lane": "resolution", "transport": "rss"},
    )


def test_strong_verification_evidence_creates_same_incident_candidate_without_merge():
    from core.intel.correlation import (
        DECISION_SAME_INCIDENT,
        associate_verification_event,
    )

    now = datetime.now(timezone.utc)
    origin = _seed_origin(now)
    before = get_incident(origin.id)
    event = _verification_event(now)
    claims = extract_humanitarian_claims(event, resolve_source_identity(event.source, event.metadata))

    decisions = associate_verification_event(event, claims)
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.decision == DECISION_SAME_INCIDENT
    assert decision.candidate_incident_id == origin.id
    assert {"temporal_proximity", "spatial_overlap", "people_count_compatible", "asset_reference_match", "independent_lineage"} <= set(decision.supporting_features)
    assert decision.review_state == "pending_review"
    assert get_incident(origin.id) == before
    assert get_incident(event.id) is None


def test_distinct_humanitarian_sources_remain_independent_on_same_x_transport():
    from core.intel.correlation import (
        DECISION_SAME_INCIDENT,
        associate_verification_event,
    )

    now = datetime.now(timezone.utc)
    _seed_origin(now)
    event = _verification_event(now)
    event.metadata.update({"platform": "x", "transport": "x"})
    claims = extract_humanitarian_claims(event, resolve_source_identity(event.source, event.metadata))

    decision = associate_verification_event(event, claims)[0]
    assert decision.source_independence_result is True
    assert decision.decision == DECISION_SAME_INCIDENT
    assert "independent_lineage" in decision.supporting_features


def test_conflicting_location_and_people_count_never_become_strong_association():
    from core.intel.correlation import DECISION_UNCERTAIN, associate_verification_event

    now = datetime.now(timezone.utc)
    _seed_origin(now, people=42)
    event = _verification_event(now, people=200, lat=40.0, lon=20.0)
    claims = extract_humanitarian_claims(event, resolve_source_identity(event.source, event.metadata))

    decision = associate_verification_event(event, claims)[0]
    assert decision.decision == DECISION_UNCERTAIN
    assert "spatial_conflict" in decision.contradicting_features
    assert "people_count_conflict" in decision.contradicting_features


def test_legacy_temporal_correlation_uses_evidence_lineage_not_display_source_family():
    from core.db.models import IntelEventDB
    from core.db.session import session_scope
    from core.intel.correlation import generate_correlation_decisions

    now = datetime.now(timezone.utc)
    origin = _seed_origin(now)
    event = IntelEvent(
        id=f"same-platform-{uuid.uuid4()}", type="distress", severity="high",
        title="another report", text="another report", source="X / Twitter",
        timestamp_utc=(now + timedelta(minutes=20)).isoformat(),
        metadata={"is_distress": True, "platform": "x"},
    )
    decisions = generate_correlation_decisions(event, lifecycle="active")
    decision = next(row for row in decisions if row.candidate_incident_id == origin.id)
    assert decision.source_independence_result is False
