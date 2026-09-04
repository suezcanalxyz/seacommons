# SPDX-License-Identifier: AGPL-3.0-or-later
"""Circular-reporting lineage (docs/updates.md P2.2).

**Goal:** "Represent derivation/quotation relationships where
detectable: original report -> article A -> article B. Independent-
source count must use evidence lineages, not URL count." Without this,
three outlets republishing the same wire report count as three
"independent" sources, inflating apparent corroboration.

v0 scope, honestly bounded: the one detectable signal available today
without new text-similarity infrastructure is an EXACT
``SourceObservationDB.raw_payload_hash`` match across two different
sources -- verbatim republication or a retweet/repost, both already
hash-identical at the byte level. ``RELATION_DERIVED_FROM`` is the only
relation this module produces; ``quotes`` (a partial excerpt, not a
verbatim copy) needs fuzzy/partial text-similarity this module does not
build -- named in NOT_YET_COMPUTABLE.

When three or more observations share one raw_payload_hash, each new
one links to the EARLIEST observation with that hash, not necessarily
its immediate quoting parent -- a genuine A -> B -> C chain collapses
to a hub-and-spoke around A. This is sufficient for
``count_independent_sources`` (the whole set still correctly collapses
to one independent source) but not for reconstructing true quotation
order -- named as a known limitation, not silently claimed as exact.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

RELATION_DERIVED_FROM = "derived_from"
METHOD_VERSION = "v0_exact_payload_hash_match"

NOT_YET_COMPUTABLE: dict[str, str] = {
    "quotation_relation": "needs fuzzy/partial text-similarity detection beyond exact hash match, not built yet",
    "exact_chain_order": "3+ observations sharing one hash collapse to a hub around the earliest one, not a reconstructed A->B->C order",
}


@dataclass(frozen=True)
class LineageEdge:
    id: str
    from_observation_id: str
    to_observation_id: str
    relation: str
    confidence: float
    method_version: str
    detected_at: str


def detect_lineage_for_observation(observation_id: str, db=None) -> Optional[LineageEdge]:
    """Looks for the earliest EARLIER observation (received_at strictly
    before this one) with the same raw_payload_hash but a different
    source_name; if found, persists one derived_from edge from this
    observation to it. Returns None (and persists nothing) when no such
    match exists -- most observations, since exact republication is the
    exception, not the rule.

    Pass ``db`` when calling from inside another caller's own
    transaction (e.g. core.intel.source_observation.record_observation,
    right after flushing the new row) -- a fresh session_scope() would
    not see that row until the outer transaction commits. Opens its own
    session_scope() when db is not given (standalone/backfill use)."""
    if db is not None:
        return _detect(db, observation_id)

    from core.db.session import session_scope

    with session_scope() as scoped_db:
        return _detect(scoped_db, observation_id)


def _detect(db, observation_id: str) -> Optional[LineageEdge]:
    from core.db.models import LineageEdgeDB, SourceObservationDB

    this_row = db.get(SourceObservationDB, observation_id)
    if this_row is None:
        return None

    earlier = (
        db.query(SourceObservationDB)
        .filter(
            SourceObservationDB.raw_payload_hash == this_row.raw_payload_hash,
            SourceObservationDB.source_name != this_row.source_name,
            SourceObservationDB.received_at < this_row.received_at,
        )
        .order_by(SourceObservationDB.received_at.asc())
        .first()
    )
    if earlier is None:
        return None

    now = datetime.now(timezone.utc)
    edge_id = str(uuid.uuid4())
    db.add(LineageEdgeDB(
        id=edge_id, from_observation_id=observation_id, to_observation_id=earlier.observation_id,
        relation=RELATION_DERIVED_FROM, confidence=0.9, method_version=METHOD_VERSION,
        detected_at=now.replace(tzinfo=None),
    ))
    db.flush()
    return LineageEdge(
        id=edge_id, from_observation_id=observation_id, to_observation_id=earlier.observation_id,
        relation=RELATION_DERIVED_FROM, confidence=0.9, method_version=METHOD_VERSION,
        detected_at=now.isoformat(),
    )


def get_lineage(observation_id: str) -> list[LineageEdge]:
    from core.db.models import LineageEdgeDB
    from core.db.session import session_scope

    with session_scope() as db:
        rows = (
            db.query(LineageEdgeDB)
            .filter(LineageEdgeDB.from_observation_id == observation_id)
            .order_by(LineageEdgeDB.detected_at.desc())
            .all()
        )
        return [
            LineageEdge(
                id=r.id, from_observation_id=r.from_observation_id,
                to_observation_id=r.to_observation_id, relation=r.relation,
                confidence=r.confidence, method_version=r.method_version,
                detected_at=r.detected_at.isoformat(),
            )
            for r in rows
        ]


def count_independent_sources(observation_ids: list[str]) -> int:
    """docs/updates.md P2.2: "Independent-source count must use evidence
    lineages, not URL count." Collapses any observation in the input set
    that derived_from another observation ALSO in the input set into the
    same group -- the group count, not len(observation_ids), is the real
    independent-source count."""
    from core.db.models import LineageEdgeDB
    from core.db.session import session_scope

    ids = set(observation_ids)
    if not ids:
        return 0

    parent: dict[str, str] = {oid: oid for oid in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    with session_scope() as db:
        edges = (
            db.query(LineageEdgeDB)
            .filter(
                LineageEdgeDB.from_observation_id.in_(ids),
                LineageEdgeDB.to_observation_id.in_(ids),
            )
            .all()
        )
        for edge in edges:
            union(edge.from_observation_id, edge.to_observation_id)

    return len({find(oid) for oid in ids})
