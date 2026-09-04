# SPDX-License-Identifier: AGPL-3.0-or-later
"""Claim + assessment model (docs/updates.md P0.4).

**Goal:** important facts (people aboard/rescued/missing/dead, ...)
become claims -- traceable, provenance-backed, coexisting when they
disagree -- not one mutable scalar overwritten by whichever report
arrived last.

v0 scope, honestly bounded: this module only extracts the PeopleCounts
fields core.intel.humanitarian_recognition.assess() already computes
(people_aboard/rescued/missing/dead/injured/intercepted/returned) --
location/vessel/outcome claims docs/updates.md P0.4 also names need
their own extraction logic (P3.3 Humanitarian geolocation V2 for
location; a later packet for vessel/outcome) and are not invented here.

The assessment strategy is deliberately simple and explicitly named:
"most recently claimed value wins," confidence fixed at a flat value
reflecting that this is unweighted recency, not a scored resolution.
docs/updates.md is explicit that a single global trust-score arbiter
must never stand in for this -- this module does not build a scoring
model; it selects openly and says so in ``method_version``. Real
contradiction detection/weighting is a later packet's job;
``contradicting_claim_ids`` is always empty here, never fabricated.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from core.intel.humanitarian_recognition import HumanitarianAssessment
from core.intel.store import IntelEvent

METHOD_VERSION = "v0_latest_claim_wins"

# HumanitarianAssessment.people field name -> claim_type. Only fields with
# a real non-None value become claims -- assess() itself distinguishes
# "not mentioned" (None) from "reported as zero" (0), and that
# distinction must survive into the claim layer.
_PEOPLE_CLAIM_TYPES = (
    "aboard", "rescued", "missing", "dead", "injured", "intercepted", "returned",
)


def claim_id(incident_id: str, claim_type: str, observation_id: str) -> str:
    """Deterministic id -- the same (incident, claim_type, observation)
    always resolves to the same row, so re-syncing an observation never
    duplicates its claims."""
    digest = hashlib.blake2s(
        f"{incident_id}:{claim_type}:{observation_id}".encode(), digest_size=12,
    ).hexdigest()
    return f"claim:{digest}"


def assessment_id(incident_id: str, field_type: str) -> str:
    digest = hashlib.blake2s(f"{incident_id}:{field_type}".encode(), digest_size=12).hexdigest()
    return f"assess:{digest}"


def record_claims_for_incident(
    incident_id: str, event: IntelEvent, assessment: HumanitarianAssessment,
) -> list[str]:
    """Persist one Claim per non-None PeopleCounts field this
    HumanitarianAssessment carries. Idempotent: re-recording the same
    observation's claims updates nothing (same claim_id, same value) --
    a claim is only ever created once per (incident, claim_type,
    observation).
    """
    from core.db.models import ClaimDB
    from core.db.session import session_scope

    recorded: list[str] = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as db:
        for field_name in _PEOPLE_CLAIM_TYPES:
            count = getattr(assessment.people, field_name, None)
            if count is None:
                continue
            claim_type = f"people_{field_name}"
            cid = claim_id(incident_id, claim_type, event.id)
            existing = db.get(ClaimDB, cid)
            if existing is not None:
                recorded.append(cid)
                continue
            db.add(ClaimDB(
                claim_id=cid, incident_id=incident_id, claim_type=claim_type,
                value={"count": count}, observation_id=event.id, source_id=event.source,
                claimed_at=event.timestamp_utc, observed_at=event.timestamp_utc,
                extraction_method="humanitarian_recognition_v2",
                verification_status="unverified", created_at=now,
            ))
            recorded.append(cid)
    return recorded


def sync_assessments_for_incident(incident_id: str) -> list[str]:
    """Recompute the "most recent claim wins" Assessment for every
    claim_type this incident currently has claims for. Never invents a
    value for a claim_type with no claims."""
    from core.db.models import AssessmentDB, ClaimDB
    from core.db.session import session_scope

    updated: list[str] = []
    with session_scope() as db:
        claim_types = [
            row[0] for row in
            db.query(ClaimDB.claim_type).filter(ClaimDB.incident_id == incident_id).distinct().all()
        ]
        for claim_type in claim_types:
            claims = (
                db.query(ClaimDB)
                .filter(ClaimDB.incident_id == incident_id, ClaimDB.claim_type == claim_type)
                .order_by(ClaimDB.claimed_at.asc())
                .all()
            )
            if not claims:
                continue
            latest = claims[-1]
            aid = assessment_id(incident_id, claim_type)
            row = db.get(AssessmentDB, aid)
            payload = dict(
                incident_id=incident_id, field_type=claim_type, value=latest.value,
                supporting_claim_ids=[c.claim_id for c in claims],
                contradicting_claim_ids=[],
                method_version=METHOD_VERSION, confidence=0.5,
            )
            if row is None:
                db.add(AssessmentDB(assessment_id=aid, **payload))
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
            updated.append(aid)
    return updated


def get_assessment(incident_id: str, field_type: str) -> Optional[dict[str, Any]]:
    from core.db.models import AssessmentDB
    from core.db.session import session_scope

    with session_scope() as db:
        row = db.get(AssessmentDB, assessment_id(incident_id, field_type))
        if row is None:
            return None
        return {
            "assessment_id": row.assessment_id,
            "incident_id": row.incident_id,
            "field_type": row.field_type,
            "value": row.value,
            "supporting_claim_ids": list(row.supporting_claim_ids or []),
            "contradicting_claim_ids": list(row.contradicting_claim_ids or []),
            "method_version": row.method_version,
            "confidence": row.confidence,
            "review_state": row.review_state,
        }
