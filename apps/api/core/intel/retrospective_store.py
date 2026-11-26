# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private, append-only case dossiers in the canonical assessment store."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
import json

from sqlalchemy.orm import Session

from core.db.models import AssessmentDB
from core.intel.retrospective_validation import ClaimDossier

FIELD_TYPE = "retrospective_event_occurrence"


def store_dossier(db: Session, dossier: ClaimDossier) -> AssessmentDB:
    """Stage one immutable dossier revision in the caller's transaction."""
    if len(dossier.episode_id) > 64:
        raise ValueError("case identifier exceeds the assessment store contract")
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
