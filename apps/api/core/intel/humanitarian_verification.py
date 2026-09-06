from __future__ import annotations

from typing import Any


def process_verification_event(event) -> dict[str, Any]:
    from core.intel.correlation import DECISION_SAME_INCIDENT, associate_verification_event
    from core.intel.humanitarian_claims import (
        extract_humanitarian_claims,
        persist_associated_claims,
    )
    from core.intel.resolution_assessment import evaluate_resolution_assessment
    from core.intel.source_identity import resolve_source_identity

    policy = resolve_source_identity(event.source, event.metadata)
    if policy.source_role != "verification":
        return {"processed": False, "reason": "not_verification_source", "associated_incident_ids": []}

    extracted = extract_humanitarian_claims(event, policy)
    try:
        from core.observability import record_humanitarian_verification_event
        record_humanitarian_verification_event(
            stage="claim_extraction", source_role=policy.source_role,
            outcome="observed" if extracted else "none",
        )
    except Exception:
        pass
    if not extracted:
        return {
            "processed": False,
            "reason": "no_verification_claims",
            "source_identity": policy.identity_id,
            "source_role": policy.source_role,
            "claim_types": [],
            "associated_incident_ids": [],
            "association_decision_ids": [],
            "resolution_assessments": [],
        }
    decisions = associate_verification_event(event, extracted)
    associated = sorted({
        decision.candidate_incident_id
        for decision in decisions
        if decision.decision == DECISION_SAME_INCIDENT and decision.candidate_incident_id
    })
    try:
        from core.observability import record_humanitarian_verification_event
        record_humanitarian_verification_event(
            stage="association", source_role=policy.source_role,
            outcome="associated" if associated else ("uncertain" if decisions else "none"),
        )
    except Exception:
        pass
    resolution_assessments: list[dict[str, Any]] = []
    for incident_id in associated:
        persist_associated_claims(incident_id, event, extracted)
        resolution = evaluate_resolution_assessment(incident_id)
        resolution_assessments.append(resolution)
        try:
            from core.observability import record_humanitarian_verification_event
            record_humanitarian_verification_event(
                stage="resolution", source_role=policy.source_role,
                outcome=str((resolution.get("value") or {}).get("outcome") or "other"),
            )
        except Exception:
            pass
        try:
            from core.intel.incident_watch import sync_watch_for_incident
            sync_watch_for_incident(incident_id)
        except Exception:
            pass

    return {
        "processed": True,
        "source_identity": policy.identity_id,
        "source_role": policy.source_role,
        "claim_types": sorted({claim.claim_type for claim in extracted}),
        "associated_incident_ids": associated,
        "association_decision_ids": [decision.id for decision in decisions],
        "resolution_assessments": resolution_assessments,
    }


def evaluate_incident_verification(incident_id: str) -> dict[str, Any]:
    from core.db.models import AssessmentDB, ClaimDB
    from core.db.session import session_scope
    from core.intel.resolution_assessment import evaluate_resolution_assessment

    resolution = evaluate_resolution_assessment(incident_id)
    with session_scope() as db:
        claim_types = sorted({
            row[0] for row in db.query(ClaimDB.claim_type).filter(ClaimDB.incident_id == incident_id).all()
        })
        mission_states = sorted({
            str((row.value or {}).get("mission_state") or "")
            for row in db.query(AssessmentDB).filter(
                AssessmentDB.incident_id == incident_id,
                AssessmentDB.field_type == "sar_mission",
            ).all()
            if (row.value or {}).get("mission_state")
        })
    return {
        "incident_id": incident_id,
        "claim_types": claim_types,
        "mission_states": mission_states,
        "resolution": resolution,
    }


def get_verification_summary(incident_id: str) -> dict[str, Any]:
    summary = evaluate_incident_verification(incident_id)
    resolution = summary["resolution"]
    return {
        "incident_id": incident_id,
        "claim_types": summary["claim_types"],
        "mission_states": summary["mission_states"],
        "resolution": {
            "assessment_id": resolution["assessment_id"],
            "value": dict(resolution["value"]),
            "method_version": resolution["method_version"],
            "review_state": resolution["review_state"],
        },
    }
