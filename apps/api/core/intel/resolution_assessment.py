from __future__ import annotations

import hashlib
from typing import Any

METHOD_VERSION = "humanitarian-resolution-v1"

_OUTCOME_CONFIDENCE = {
    "no_resolution_evidence": 0.2,
    "response_detected": 0.5,
    "rescue_activity_probable": 0.7,
    "rescue_confirmed": 0.9,
    "disembarkation_confirmed": 0.92,
    "fatal_outcome_reported": 0.9,
    "contradictory_evidence": 0.35,
    "insufficient_evidence": 0.3,
}


def resolution_assessment_id(incident_id: str) -> str:
    digest = hashlib.blake2s(f"{incident_id}:resolution".encode(), digest_size=16).hexdigest()
    return f"resolution:{digest}"


def _strong_association(db, incident_id: str, observation_id: str) -> bool:
    from core.db.models import CorrelationDecisionDB

    rows = db.query(CorrelationDecisionDB).filter(
        CorrelationDecisionDB.observation_id == observation_id,
        CorrelationDecisionDB.candidate_incident_id == incident_id,
    ).all()
    return any(
        row.decision == "SAME_INCIDENT"
        and bool(row.source_independence_result)
        and float(row.confidence or 0) >= 0.8
        and not list(row.contradicting_features or [])
        for row in rows
    )


def _mission_outcome(rows) -> str | None:
    states = {str((row.value or {}).get("mission_state") or "") for row in rows}
    if "probable_rescue_activity" in states:
        return "rescue_activity_probable"
    if states.intersection({"approaching", "on_scene", "possible_response"}):
        return "response_detected"
    return None


def _select_outcome(db, incident_id: str) -> tuple[str, list[str], list[str], list[str]]:
    from core.db.models import AssessmentDB, ClaimDB

    claims = db.query(ClaimDB).filter(ClaimDB.incident_id == incident_id).all()
    strong = [claim for claim in claims if _strong_association(db, incident_id, claim.observation_id)]
    strong_types = {claim.claim_type for claim in strong}
    all_types = {claim.claim_type for claim in claims}

    supporting: list[str] = []
    contradicting: list[str] = []
    reasons: list[str] = []

    if "contradictory_update" in strong_types:
        contradicting = [claim.claim_id for claim in strong if claim.claim_type == "contradictory_update"]
        supporting = [claim.claim_id for claim in strong if claim.claim_type != "contradictory_update"]
        return "contradictory_evidence", supporting, contradicting, ["STRONG_CONTRADICTORY_CLAIM"]
    if "disembarkation_reported" in strong_types:
        supporting = [claim.claim_id for claim in strong if claim.claim_type == "disembarkation_reported"]
        return "disembarkation_confirmed", supporting, [], ["STRONG_DISEMBARKATION_CLAIM"]
    if "fatality_reported" in strong_types:
        supporting = [claim.claim_id for claim in strong if claim.claim_type == "fatality_reported"]
        return "fatal_outcome_reported", supporting, [], ["STRONG_FATALITY_CLAIM"]
    if "rescue_completed" in strong_types:
        supporting = [claim.claim_id for claim in strong if claim.claim_type == "rescue_completed"]
        return "rescue_confirmed", supporting, [], ["STRONG_RESCUE_COMPLETED_CLAIM"]

    resolution_shaped = {
        "rescue_completed", "disembarkation_reported", "fatality_reported",
        "case_resolved_statement", "contradictory_update",
    }
    if all_types.intersection(resolution_shaped):
        return "insufficient_evidence", [], [], ["RESOLUTION_CLAIM_WEAK_ASSOCIATION"]

    missions = db.query(AssessmentDB).filter(
        AssessmentDB.incident_id == incident_id,
        AssessmentDB.field_type == "sar_mission",
    ).all()
    mission_outcome = _mission_outcome(missions)
    if mission_outcome:
        return mission_outcome, [], [], [f"SAR_MISSION_{mission_outcome.upper()}"]
    return "no_resolution_evidence", [], [], ["NO_RESOLUTION_EVIDENCE"]


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "assessment_id": row.assessment_id,
        "incident_id": row.incident_id,
        "field_type": row.field_type,
        "value": dict(row.value or {}),
        "supporting_claim_ids": list(row.supporting_claim_ids or []),
        "contradicting_claim_ids": list(row.contradicting_claim_ids or []),
        "method_version": row.method_version,
        "confidence": row.confidence,
        "review_state": row.review_state,
    }


def evaluate_resolution_assessment(incident_id: str) -> dict[str, Any]:
    from core.db.models import AssessmentDB
    from core.db.session import session_scope

    aid = resolution_assessment_id(incident_id)
    with session_scope() as db:
        outcome, supporting, contradicting, reasons = _select_outcome(db, incident_id)
        review_state = "needs_review" if outcome in {"contradictory_evidence", "insufficient_evidence"} else "unreviewed"
        value = {
            "outcome": outcome,
            "reason_codes": reasons,
            "evidence_stage": (
                "confirmed" if outcome in {"rescue_confirmed", "disembarkation_confirmed", "fatal_outcome_reported"}
                else "derived"
            ),
        }
        row = db.get(AssessmentDB, aid)
        if row is None:
            row = AssessmentDB(
                assessment_id=aid, incident_id=incident_id, field_type="resolution",
                value=value, supporting_claim_ids=supporting,
                contradicting_claim_ids=contradicting, method_version=METHOD_VERSION,
                confidence=_OUTCOME_CONFIDENCE[outcome], review_state=review_state,
            )
            db.add(row)
            db.flush()
        else:
            row.value = value
            row.supporting_claim_ids = supporting
            row.contradicting_claim_ids = contradicting
            row.method_version = METHOD_VERSION
            row.confidence = _OUTCOME_CONFIDENCE[outcome]
            row.review_state = review_state
        return _row_to_dict(row)
