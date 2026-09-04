# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistence for core.intel.hypothesis.InvestigationHypothesis (docs/fixes.md M14.3).

core.intel.hypothesis is deliberately pure (no DB reference at all) so its
lifecycle/gate logic stays testable in isolation. This module is the thin,
separately-tested boundary that converts an InvestigationHypothesis to and
from core.db.models.InvestigationHypothesisDB -- the only place either side
of that conversion happens.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from core.intel.hypothesis import AuditEntry, InvestigationHypothesis


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _audit_entry_to_dict(entry: AuditEntry) -> dict:
    return {
        "actor": entry.actor,
        "timestamp": _iso(entry.timestamp),
        "old_state": entry.old_state,
        "new_state": entry.new_state,
        "evidence_snapshot_hash": entry.evidence_snapshot_hash,
    }


def _audit_entry_from_dict(data: dict) -> AuditEntry:
    return AuditEntry(
        actor=str(data.get("actor") or ""),
        timestamp=_parse_iso(data["timestamp"]),
        old_state=data.get("old_state"),
        new_state=str(data.get("new_state") or ""),
        evidence_snapshot_hash=str(data.get("evidence_snapshot_hash") or ""),
    )


def to_row_kwargs(hypothesis: InvestigationHypothesis) -> dict:
    """The InvestigationHypothesisDB column values for one hypothesis --
    exposed separately from save_hypothesis() so a caller doing a batch
    write can build many of these without opening a session per row."""
    return {
        "hypothesis_id": hypothesis.hypothesis_id,
        "hypothesis_type": hypothesis.hypothesis_type,
        "subject_ids": list(hypothesis.subject_ids),
        "state": hypothesis.state,
        "reason_codes": list(hypothesis.reason_codes),
        "counter_indicators": list(hypothesis.counter_indicators),
        "evidence_links": list(hypothesis.evidence_links),
        "evidence_stage": hypothesis.evidence_stage,
        "has_unresolved_blocking_identity_conflict": hypothesis.has_unresolved_blocking_identity_conflict,
        "allegation_shaped_wording": hypothesis.allegation_shaped_wording,
        "explicit_review_done": hypothesis.explicit_review_done,
        "audit_history": [_audit_entry_to_dict(e) for e in hypothesis.audit_history],
    }


def _from_row(row) -> InvestigationHypothesis:
    return InvestigationHypothesis(
        hypothesis_id=row.hypothesis_id,
        hypothesis_type=row.hypothesis_type,
        subject_ids=tuple(row.subject_ids or ()),
        state=row.state,
        reason_codes=tuple(row.reason_codes or ()),
        counter_indicators=tuple(row.counter_indicators or ()),
        evidence_links=tuple(row.evidence_links or ()),
        evidence_stage=row.evidence_stage,
        has_unresolved_blocking_identity_conflict=bool(row.has_unresolved_blocking_identity_conflict),
        allegation_shaped_wording=bool(row.allegation_shaped_wording),
        explicit_review_done=bool(row.explicit_review_done),
        audit_history=tuple(_audit_entry_from_dict(e) for e in (row.audit_history or ())),
    )


def get_hypothesis(hypothesis_id: str) -> Optional[InvestigationHypothesis]:
    from core.db.models import InvestigationHypothesisDB
    from core.db.session import session_scope

    with session_scope() as db:
        row = db.query(InvestigationHypothesisDB).filter(
            InvestigationHypothesisDB.hypothesis_id == hypothesis_id
        ).first()
        return _from_row(row) if row is not None else None


def save_hypothesis(hypothesis: InvestigationHypothesis) -> None:
    """Upsert by hypothesis_id -- callers always pass the full current
    dataclass state (core.intel.hypothesis.transition() returns a new
    instance rather than mutating), so this always replaces every column,
    same convention as core.db.store's other upsert-by-id writers."""
    from core.db.models import InvestigationHypothesisDB
    from core.db.session import session_scope

    kwargs = to_row_kwargs(hypothesis)
    with session_scope() as db:
        row = db.query(InvestigationHypothesisDB).filter(
            InvestigationHypothesisDB.hypothesis_id == hypothesis.hypothesis_id
        ).first()
        if row is None:
            db.add(InvestigationHypothesisDB(**kwargs))
        else:
            for key, value in kwargs.items():
                setattr(row, key, value)


def list_hypotheses(
    *, hypothesis_type: Optional[str] = None, state: Optional[str] = None, limit: int = 200,
) -> list[InvestigationHypothesis]:
    from core.db.models import InvestigationHypothesisDB
    from core.db.session import session_scope

    with session_scope() as db:
        q = db.query(InvestigationHypothesisDB)
        if hypothesis_type is not None:
            q = q.filter(InvestigationHypothesisDB.hypothesis_type == hypothesis_type)
        if state is not None:
            q = q.filter(InvestigationHypothesisDB.state == state)
        rows = q.order_by(InvestigationHypothesisDB.updated_at.desc()).limit(limit).all()
        return [_from_row(r) for r in rows]
