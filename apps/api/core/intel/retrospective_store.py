# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private, append-only case dossiers in the canonical assessment store."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
import json

from sqlalchemy.orm import Session
from sqlalchemy import select

from core.db.models import AssessmentDB
from core.intel.retrospective_validation import METHOD, ClaimDossier

FIELD_TYPE = "retrospective_event_occurrence"
OCCURRENCE_CLAIM = "event_occurrence"


def store_dossier(db: Session, dossier: ClaimDossier) -> AssessmentDB:
    """Stage one immutable dossier revision in the caller's transaction."""
    if len(dossier.episode_id) > 64:
        raise ValueError("case identifier exceeds the assessment store contract")
    if dossier.claim_id != OCCURRENCE_CLAIM:
        raise ValueError("case visibility is reserved for occurrence assessments")
    encoded = json.dumps(
        asdict(dossier), sort_keys=True, separators=(",", ":"),
        default=datetime.isoformat,
    )
    revision_id = "retro:" + hashlib.sha256(encoded.encode()).hexdigest()
    existing = db.get(AssessmentDB, revision_id)
    if existing is not None:
        return existing
    document = json.loads(encoded)
    row = AssessmentDB(
        assessment_id=revision_id,
        incident_id=dossier.episode_id,
        field_type=FIELD_TYPE,
        method_version=dossier.method,
        review_state="reviewed" if dossier.reviewed_by else "unreviewed",
        value=document,
    )
    db.add(row)
    return row


def refuted_case_ids(db: Session, case_ids: set[str] | None = None) -> set[str]:
    """Resolve the latest reviewed occurrence decision for each canonical case."""
    statement = select(AssessmentDB).where(
        AssessmentDB.field_type == FIELD_TYPE, AssessmentDB.review_state == "reviewed",
        AssessmentDB.method_version == METHOD,
    )
    if case_ids is not None:
        if not case_ids:
            return set()
        statement = statement.where(AssessmentDB.incident_id.in_(case_ids))
    rows = db.scalars(statement.order_by(
        AssessmentDB.created_at.desc(), AssessmentDB.assessment_id.desc(),
    ))
    seen = set()
    refuted = set()
    for row in rows:
        if row.incident_id in seen:
            continue
        seen.add(row.incident_id)
        value = row.value
        if (
            isinstance(value, dict) and value.get("episode_id") == row.incident_id
            and value.get("claim_id") == OCCURRENCE_CLAIM and value.get("method") == METHOD
            and value.get("classification") == "false_positive"
            and value.get("reviewed_by") and value.get("review_reason")
        ):
            refuted.add(row.incident_id)
    return refuted
