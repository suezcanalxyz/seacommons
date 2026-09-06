# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from core.review.contracts import ReviewRecord
from core.review.ledger import persist_review

@dataclass(frozen=True)
class HumanitarianReviewResult:
    review_id: str
    applied: bool
    replayed: bool
    lifecycle: str


def apply_humanitarian_review(record: ReviewRecord) -> HumanitarianReviewResult:
    if record.target_type != 'humanitarian_resolution':
        raise ValueError('target_type must be humanitarian_resolution')
    persisted = persist_review(record)
    from core.db.models import AssessmentDB, HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import session_scope
    with session_scope() as db:
        assessment = db.get(AssessmentDB, record.target_id)
        if assessment is None or assessment.field_type != 'resolution':
            raise ValueError('review target not found')
        if assessment.method_version != record.target_version:
            raise ValueError('target_version does not match current assessment')
        incident = db.get(HumanitarianIncidentDB, assessment.incident_id)
        if incident is None:
            raise ValueError('incident not found')
        prior = db.query(IncidentTransitionDB).filter(IncidentTransitionDB.review_decision_id == record.review_id).first()
        if prior is not None:
            return HumanitarianReviewResult(record.review_id, True, True, incident.lifecycle)
        if record.decision == 'reject':
            assessment.review_state = 'rejected'
            incident.review_status = 'rejected'
            return HumanitarianReviewResult(record.review_id, False, persisted.replayed, incident.lifecycle)
        if record.decision == 'needs_more_evidence':
            assessment.review_state = 'needs_review'
            incident.review_status = 'needs_more_evidence'
            return HumanitarianReviewResult(record.review_id, False, persisted.replayed, incident.lifecycle)
        target = record.requested_transition
        if target not in {'active','resolved','needs_review'}:
            raise ValueError('requested_transition unsupported for Humanitarian review')
        previous = incident.lifecycle
        assessment.review_state = 'approved'
        incident.review_status = 'approved'
        if previous != target:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            incident.lifecycle = target
            incident.incident_status = {'resolved':'resolved','needs_review':'needs_review'}.get(target,'active')
            incident.state_changed_at = now
            incident.revision = (incident.revision or 1) + 1
            if target == 'resolved' and incident.resolved_at is None:
                incident.resolved_at = now
            db.add(IncidentTransitionDB(
                transition_id=f'trans:review:{record.review_id}', incident_id=incident.incident_id,
                from_state=previous, to_state=target, transition_at=now,
                effective_at=record.reviewed_at.isoformat(), reason_code='explicit_review_approval',
                supporting_observation_ids=list(incident.source_observation_ids or []),
                contradicting_observation_ids=[], method_version='review-v0', confidence=None,
                review_required=False, review_decision_id=record.review_id,
            ))
        return HumanitarianReviewResult(record.review_id, True, persisted.replayed, incident.lifecycle)
