# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

def recent_review_summary(*, limit: int = 50) -> dict:
    from core.db.models import ReviewRecordDB
    from core.db.session import session_scope
    bounded = max(1, min(int(limit), 200))
    with session_scope() as db:
        rows = db.query(ReviewRecordDB).order_by(ReviewRecordDB.reviewed_at.desc()).limit(bounded).all()
        items = [{
            "review_id": r.review_id,
            "target_type": r.target_type,
            "decision": r.decision,
            "requested_transition": r.requested_transition,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            "actor": r.actor,
        } for r in rows]
    return {"total": len(items), "items": items}
