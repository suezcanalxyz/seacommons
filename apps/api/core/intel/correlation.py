# SPDX-License-Identifier: AGPL-3.0-or-later
"""CorrelationDecision (docs/updates.md P2.1).

**Goal:** "Model similarity cannot be sole merge evidence." Two
independently-reported posts about the same real-world case currently
become two separate ``HumanitarianIncidentDB`` rows (docs/updates.md
P0.3's own named limitation) -- this module is the first step toward
recognising that, WITHOUT ever auto-merging: every decision this
module produces is a candidate pairing persisted for analyst review
(``review_state="pending_review"``), never an automatic incident
merge or re-key. Merging incidents is separate, later, deliberately
higher-friction work this packet does not perform.

v0 scope, honestly bounded: docs/updates.md P2.1 names a ten-step
candidate-generation order (exact thread/source IDs -> known source-
specific case IDs -> temporal bounds -> spatial overlap -> place/route
compatibility -> people-count range -> vessel description -> NGO/
authority references -> lexical/entity overlap -> optional embedding/
reranker). This module implements only step 3, temporal bounds --
the one signal available today without new extraction logic (spatial
needs P3.3 geolocation v2 for humanitarian text; lexical/vessel/NGO
matching need new extraction this packet does not invent). A found
temporal candidate is always classified UNCERTAIN, never SAME_INCIDENT
-- co-occurring in time is suggestive, never sufficient on its own,
matching the invariant this packet exists to enforce. Steps 1-2 and
4-10 are named in NOT_YET_COMPUTABLE.

``source_independence_result`` reuses P1.1's ``core.intel.
source_catalog`` independence_group -- two candidates sharing a group
(e.g. both X/Twitter-based) are flagged as NOT independent
corroboration of each other, exactly the reasoning P1.1 introduced
that field for.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

DECISION_SAME_INCIDENT = "SAME_INCIDENT"
DECISION_RELATED_INCIDENT = "RELATED_INCIDENT"
DECISION_NEW_INCIDENT = "NEW_INCIDENT"
DECISION_UNCERTAIN = "UNCERTAIN"

METHOD_VERSION = "v0_temporal_candidate_only"
TEMPORAL_CANDIDATE_WINDOW_HOURS = 6
_OPEN_LIFECYCLES = ("active", "needs_review")

NOT_YET_COMPUTABLE: dict[str, str] = {
    "exact_thread_source_id_match": "needs a general cross-adapter thread/quote-relationship signal",
    "known_source_specific_case_id": "needs per-source case-id extraction, not built yet",
    "spatial_overlap": "needs P3.3 Humanitarian geolocation v2",
    "place_route_departure_compatibility": "needs place/route extraction, not built yet",
    "people_count_range": "needs candidate-incident people-count comparison logic, not built yet",
    "vessel_description_identity": "needs vessel-description extraction, not built yet",
    "ngo_authority_references": "needs NGO/authority-entity extraction, not built yet",
    "lexical_entity_overlap": "needs entity extraction, not built yet",
    "embedding_reranker": "explicitly optional in docs/updates.md P2.1; not built",
}


@dataclass(frozen=True)
class CorrelationDecision:
    id: str
    observation_id: str
    candidate_incident_id: Optional[str]
    decision: str
    supporting_features: list[str]
    contradicting_features: list[str]
    source_independence_result: Optional[bool]
    method_version: str
    confidence: float
    review_state: str
    created_at: str


def _source_family(source_name: str) -> Optional[str]:
    from core.intel.source_catalog import get_source_profile

    profile = get_source_profile(source_name)
    return profile["source_family"] if profile is not None else None


def generate_correlation_decisions(event, *, lifecycle: str) -> list[CorrelationDecision]:
    """Real DB-querying entry point. Finds open humanitarian incidents
    (excluding this event's own incident_id) whose reported_at falls
    within TEMPORAL_CANDIDATE_WINDOW_HOURS of this event, persists one
    UNCERTAIN CorrelationDecision per candidate found, and one
    NEW_INCIDENT decision (no candidate) when none are found. Never
    raises -- callers in an intel_store subscriber already isolate
    exceptions, but this stays defensive since it may also run from a
    backfill script."""
    from core.db.models import HumanitarianIncidentDB, IntelEventDB
    from core.db.session import session_scope
    from core.intel.lifecycle import parse_utc

    event_ts = parse_utc(event.timestamp_utc)
    if event_ts is None:
        return []

    window_start = (event_ts - timedelta(hours=TEMPORAL_CANDIDATE_WINDOW_HOURS)).isoformat()
    window_end = (event_ts + timedelta(hours=TEMPORAL_CANDIDATE_WINDOW_HOURS)).isoformat()
    now = datetime.now(timezone.utc)

    decisions: list[CorrelationDecision] = []
    with session_scope() as db:
        candidates = (
            db.query(HumanitarianIncidentDB)
            .filter(
                HumanitarianIncidentDB.incident_id != event.id,
                HumanitarianIncidentDB.lifecycle.in_(_OPEN_LIFECYCLES),
                HumanitarianIncidentDB.reported_at >= window_start,
                HumanitarianIncidentDB.reported_at <= window_end,
            )
            .all()
        )

        if not candidates:
            row = _persist(db, observation_id=event.id, candidate_incident_id=None,
                            decision=DECISION_NEW_INCIDENT, supporting_features=[],
                            contradicting_features=[], source_independence_result=None,
                            confidence=1.0, now=now)
            return [row]

        own_family = _source_family(event.source)
        for candidate in candidates:
            founding_event = db.get(IntelEventDB, candidate.incident_id)
            candidate_family = _source_family(founding_event.source) if founding_event else None
            independence = (
                own_family is not None and candidate_family is not None and own_family != candidate_family
            )
            row = _persist(
                db, observation_id=event.id, candidate_incident_id=candidate.incident_id,
                decision=DECISION_UNCERTAIN, supporting_features=["temporal_proximity"],
                contradicting_features=[], source_independence_result=independence,
                confidence=0.3, now=now,
            )
            decisions.append(row)
    return decisions


def _persist(
    db, *, observation_id: str, candidate_incident_id: Optional[str], decision: str,
    supporting_features: list[str], contradicting_features: list[str],
    source_independence_result: Optional[bool], confidence: float, now: datetime,
) -> CorrelationDecision:
    from core.db.models import CorrelationDecisionDB

    row_id = str(uuid.uuid4())
    db.add(CorrelationDecisionDB(
        id=row_id, observation_id=observation_id, candidate_incident_id=candidate_incident_id,
        decision=decision, supporting_features=supporting_features,
        contradicting_features=contradicting_features,
        source_independence_result=source_independence_result,
        method_version=METHOD_VERSION, confidence=confidence,
        review_state="pending_review", created_at=now.replace(tzinfo=None),
    ))
    db.flush()
    return CorrelationDecision(
        id=row_id, observation_id=observation_id, candidate_incident_id=candidate_incident_id,
        decision=decision, supporting_features=supporting_features,
        contradicting_features=contradicting_features,
        source_independence_result=source_independence_result,
        method_version=METHOD_VERSION, confidence=confidence,
        review_state="pending_review", created_at=now.isoformat(),
    )


def get_correlation_decisions(observation_id: str) -> list[CorrelationDecision]:
    from core.db.models import CorrelationDecisionDB
    from core.db.session import session_scope

    with session_scope() as db:
        rows = (
            db.query(CorrelationDecisionDB)
            .filter(CorrelationDecisionDB.observation_id == observation_id)
            .order_by(CorrelationDecisionDB.created_at.desc())
            .all()
        )
        return [
            CorrelationDecision(
                id=r.id, observation_id=r.observation_id,
                candidate_incident_id=r.candidate_incident_id, decision=r.decision,
                supporting_features=list(r.supporting_features or []),
                contradicting_features=list(r.contradicting_features or []),
                source_independence_result=r.source_independence_result,
                method_version=r.method_version, confidence=r.confidence,
                review_state=r.review_state, created_at=r.created_at.isoformat(),
            )
            for r in rows
        ]
