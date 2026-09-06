# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
from dataclasses import dataclass
from core.db.models import ReviewRecordDB
from core.db.session import session_scope
from core.review.contracts import ReviewRecord

@dataclass(frozen=True)
class PersistedReview:
    review_id: str
    replayed: bool

def persist_review(record: ReviewRecord) -> PersistedReview:
    with session_scope() as db:
        existing=db.get(ReviewRecordDB, record.review_id)
        if existing is not None:
            return PersistedReview(record.review_id, True)
        db.add(ReviewRecordDB(
            review_id=record.review_id,target_type=record.target_type,target_id=record.target_id,
            target_version=record.target_version,evidence_snapshot_id=record.evidence_snapshot_id,
            decision=record.decision,rationale=record.rationale,actor=record.actor,
            reviewed_at=record.reviewed_at.replace(tzinfo=None),requested_transition=record.requested_transition,
        ))
        db.flush()
        return PersistedReview(record.review_id, False)
