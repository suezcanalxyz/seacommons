from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _tables():
    from core.db.models import AssessmentDB, ClaimDB, CorrelationDecisionDB
    from core.db.session import engine, session_scope

    for table in (ClaimDB.__table__, CorrelationDecisionDB.__table__, AssessmentDB.__table__):
        table.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(AssessmentDB).delete()
        db.query(CorrelationDecisionDB).delete()
        db.query(ClaimDB).delete()
    yield


def _claim(incident_id: str, claim_type: str, observation_id: str, *, value=None):
    from core.db.models import ClaimDB
    from core.db.session import session_scope

    with session_scope() as db:
        db.add(ClaimDB(
            claim_id=f"claim:{observation_id}:{claim_type}", incident_id=incident_id,
            claim_type=claim_type, value=value or {}, observation_id=observation_id,
            source_id="SOS Méditerranée", claimed_at=datetime.now(timezone.utc).isoformat(),
            observed_at=datetime.now(timezone.utc).isoformat(), extraction_method="test",
            verification_status="unverified",
        ))


def _association(incident_id: str, observation_id: str, *, strong: bool):
    from core.db.models import CorrelationDecisionDB
    from core.db.session import session_scope

    with session_scope() as db:
        db.add(CorrelationDecisionDB(
            id=f"corr:{observation_id}", observation_id=observation_id,
            candidate_incident_id=incident_id,
            decision="SAME_INCIDENT" if strong else "UNCERTAIN",
            supporting_features=["temporal_proximity", "spatial_overlap"] if strong else ["temporal_proximity"],
            contradicting_features=[], source_independence_result=True if strong else None,
            method_version="test", confidence=0.9 if strong else 0.3,
            review_state="pending_review",
        ))


def _mission(incident_id: str, state: str):
    from core.db.models import AssessmentDB
    from core.db.session import session_scope

    with session_scope() as db:
        db.add(AssessmentDB(
            assessment_id=f"sar:{incident_id}", incident_id=incident_id,
            field_type="sar_mission", value={"mission_state": state, "independence_groups": ["ais_sensor_lineage"]},
            supporting_claim_ids=[], contradicting_claim_ids=[], method_version="test",
            confidence=0.7, review_state="unreviewed",
        ))


def test_no_evidence_yields_no_resolution_evidence():
    from core.intel.resolution_assessment import evaluate_resolution_assessment

    result = evaluate_resolution_assessment("incident-none")
    assert result["value"]["outcome"] == "no_resolution_evidence"


def test_ais_response_and_probable_activity_are_bounded_below_confirmation():
    from core.intel.resolution_assessment import evaluate_resolution_assessment

    _mission("incident-response", "approaching")
    assert evaluate_resolution_assessment("incident-response")["value"]["outcome"] == "response_detected"

    _mission("incident-probable", "probable_rescue_activity")
    assert evaluate_resolution_assessment("incident-probable")["value"]["outcome"] == "rescue_activity_probable"


def test_strong_first_party_rescue_claim_can_confirm_but_weak_match_cannot():
    from core.intel.resolution_assessment import evaluate_resolution_assessment

    _claim("incident-strong", "rescue_completed", "obs-strong")
    _association("incident-strong", "obs-strong", strong=True)
    strong = evaluate_resolution_assessment("incident-strong")
    assert strong["value"]["outcome"] == "rescue_confirmed"
    assert strong["review_state"] == "unreviewed"

    _claim("incident-weak", "rescue_completed", "obs-weak")
    _association("incident-weak", "obs-weak", strong=False)
    weak = evaluate_resolution_assessment("incident-weak")
    assert weak["value"]["outcome"] == "insufficient_evidence"
    assert weak["review_state"] == "needs_review"


def test_contradictory_strong_claim_overrides_resolution():
    from core.intel.resolution_assessment import evaluate_resolution_assessment

    _claim("incident-contradict", "rescue_completed", "obs-rescue")
    _association("incident-contradict", "obs-rescue", strong=True)
    _claim("incident-contradict", "contradictory_update", "obs-correction")
    _association("incident-contradict", "obs-correction", strong=True)

    result = evaluate_resolution_assessment("incident-contradict")
    assert result["value"]["outcome"] == "contradictory_evidence"
    assert result["review_state"] == "needs_review"


@pytest.mark.parametrize(
    ("claim_type", "expected"),
    [
        ("disembarkation_reported", "disembarkation_confirmed"),
        ("fatality_reported", "fatal_outcome_reported"),
    ],
)
def test_high_specificity_outcomes_require_strong_association(claim_type, expected):
    from core.intel.resolution_assessment import evaluate_resolution_assessment

    incident_id = f"incident-{claim_type}"
    observation_id = f"obs-{claim_type}"
    _claim(incident_id, claim_type, observation_id)
    _association(incident_id, observation_id, strong=True)
    assert evaluate_resolution_assessment(incident_id)["value"]["outcome"] == expected


def test_replay_updates_same_resolution_assessment_id():
    from core.db.models import AssessmentDB
    from core.db.session import session_scope
    from core.intel.resolution_assessment import evaluate_resolution_assessment

    first = evaluate_resolution_assessment("incident-replay")
    second = evaluate_resolution_assessment("incident-replay")
    assert first["assessment_id"] == second["assessment_id"]
    with session_scope() as db:
        assert db.query(AssessmentDB).filter_by(incident_id="incident-replay", field_type="resolution").count() == 1
