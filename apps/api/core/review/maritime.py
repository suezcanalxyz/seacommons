# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
from dataclasses import dataclass, replace
from core.review.contracts import ReviewRecord
from core.review.ledger import persist_review

@dataclass(frozen=True)
class MaritimeReviewResult:
    review_id: str
    applied: bool
    replayed: bool
    state: str


def apply_maritime_review(record: ReviewRecord) -> MaritimeReviewResult:
    if record.target_type != 'maritime_hypothesis':
        raise ValueError('target_type must be maritime_hypothesis')
    persisted = persist_review(record)
    from core.intel.hypothesis import transition
    from core.intel.hypothesis_store import get_hypothesis, save_hypothesis
    hypothesis = get_hypothesis(record.target_id)
    if hypothesis is None:
        raise ValueError('review target not found')

    # Exact replay: if this review already produced an audit entry, do not append another.
    review_actor = f'review:{record.actor}'
    if any(entry.actor == review_actor for entry in hypothesis.audit_history):
        return MaritimeReviewResult(record.review_id, True, True, hypothesis.state)

    if hypothesis.state != record.target_version:
        raise ValueError('target_version does not match current hypothesis state')

    if record.decision == 'needs_more_evidence':
        return MaritimeReviewResult(record.review_id, False, persisted.replayed, hypothesis.state)

    if record.decision == 'reject':
        reviewed = replace(hypothesis, explicit_review_done=True)
        reviewed = transition(reviewed, 'rejected', actor=review_actor)
        save_hypothesis(reviewed)
        return MaritimeReviewResult(record.review_id, True, persisted.replayed, reviewed.state)

    reviewed = replace(hypothesis, explicit_review_done=True)
    target = record.requested_transition
    if target is None:
        raise ValueError('requested_transition is required')
    if target == reviewed.state:
        save_hypothesis(reviewed)
        return MaritimeReviewResult(record.review_id, True, persisted.replayed, reviewed.state)
    reviewed = transition(reviewed, target, actor=review_actor)
    save_hypothesis(reviewed)
    return MaritimeReviewResult(record.review_id, True, persisted.replayed, reviewed.state)
