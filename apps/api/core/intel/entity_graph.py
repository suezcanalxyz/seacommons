# SPDX-License-Identifier: AGPL-3.0-or-later
"""Entity graph (docs/updates.md P2.3).

**Goal:** "Canonical entities may include: vessel, organisation, source
account, port, place, maritime zone, infrastructure, incident, episode,
observation. Relationships carry provenance and time bounds." "Do not
force the entire platform into a graph database prematurely. Start with
typed relational objects/edges in PostgreSQL; evaluate specialized
graph infrastructure only if measured queries justify it."

v0 scope, honestly bounded: this module is the generic entity/edge
schema plus ``get_or_create_entity`` (idempotent by (entity_type,
canonical_key)) and ``record_relationship`` (append-only, provenanced,
time-bounded). It does NOT backfill every existing object in this
codebase into the graph -- that would duplicate authorities that
already exist (e.g. re-modeling every SourceObservationDB row as a
generic "observation" entity for every field it already has would
violate docs/updates.md invariant #17, "one authoritative path per
concept"). Instead it wires exactly the two relation types that are
already real, detected signals with nothing new to invent:

  - ``reported_by``: every newly recorded SourceObservation implies an
    "observation" entity reported_by a "source account" entity --
    mechanical, from fields that already exist (observation_id,
    source_name), wired into core.intel.source_observation.
    record_observation (same transaction).
  - ``derived_from``: projects core.intel.circular_reporting's (P2.2)
    already-detected lineage edges into the graph as a relationship
    between two "observation" entities -- the graph becomes a queryable
    superset view across relation types, not a second detector.

Every other named entity type (vessel, organisation, port, place,
maritime zone, infrastructure, incident, episode) and every other named
relation type (mentions, located_at, near, responding_to, involved_in,
observed_as, same_as_candidate, corroborates, contradicts, supersedes)
has no producer yet -- named in NOT_YET_WIRED rather than silently
absent, since each needs its own extraction/detection logic this packet
does not invent (place/vessel extraction, correlation-to-corroboration
promotion policy, etc.).
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

ENTITY_TYPES = (
    "vessel", "organisation", "source_account", "port", "place",
    "maritime_zone", "infrastructure", "incident", "episode", "observation",
)
RELATION_TYPES = (
    "reported_by", "mentions", "located_at", "near", "responding_to",
    "involved_in", "observed_as", "same_as_candidate", "corroborates",
    "contradicts", "supersedes", "derived_from",
)

NOT_YET_WIRED: dict[str, str] = {
    "vessel": "needs vessel-identity extraction/canonicalization, not built yet",
    "organisation": "needs NGO/authority-entity extraction, not built yet",
    "port": "needs place/port extraction, not built yet",
    "place": "needs place extraction, not built yet",
    "maritime_zone": "needs zone-membership derivation, not built yet",
    "infrastructure": "needs infrastructure-entity extraction, not built yet",
    "incident": "HumanitarianIncidentDB remains authoritative on its own; not yet projected into this graph",
    "episode": "vessel-episode objects remain authoritative on their own; not yet projected into this graph",
    "mentions": "needs entity extraction from free text, not built yet",
    "located_at": "needs place extraction, not built yet",
    "near": "needs place/zone proximity derivation, not built yet",
    "responding_to": "needs a rescuing-vessel/authority extraction signal, not built yet",
    "involved_in": "needs entity-to-incident linkage beyond reported_by, not built yet",
    "observed_as": "needs AIS/vessel-identity cross-referencing, not built yet",
    "same_as_candidate": "needs promotion policy from P2.1 CorrelationDecision, not built yet",
    "corroborates": "needs a reviewed-and-accepted CorrelationDecision, not auto-derived from an UNCERTAIN one",
    "contradicts": "needs contradiction detection beyond P0.4's claim model, not built yet",
    "supersedes": "needs an explicit supersession signal beyond P0.7 Drift ownership, not built yet",
}


@dataclass(frozen=True)
class Entity:
    entity_id: str
    entity_type: str
    canonical_key: str
    display_name: Optional[str]
    attributes: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class EntityRelationship:
    id: str
    from_entity_id: str
    to_entity_id: str
    relation_type: str
    provenance: dict[str, Any]
    valid_from: Optional[str]
    valid_to: Optional[str]
    confidence: float
    method_version: str
    created_at: str


def entity_id(entity_type: str, canonical_key: str) -> str:
    """Deterministic id from (entity_type, canonical_key) -- what makes
    get_or_create_entity idempotent."""
    digest = hashlib.blake2s(f"{entity_type}:{canonical_key}".encode(), digest_size=16).hexdigest()
    return f"ent:{digest}"


def get_or_create_entity(
    db, *, entity_type: str, canonical_key: str,
    display_name: Optional[str] = None, attributes: Optional[dict[str, Any]] = None,
) -> Entity:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"entity_type must be one of {ENTITY_TYPES}, got {entity_type!r}")

    from core.db.models import EntityDB

    eid = entity_id(entity_type, canonical_key)
    existing = db.get(EntityDB, eid)
    if existing is not None:
        return _entity_from_row(existing)

    now = datetime.now(timezone.utc)
    row = EntityDB(
        entity_id=eid, entity_type=entity_type, canonical_key=canonical_key,
        display_name=display_name, attributes=dict(attributes or {}),
        created_at=now.replace(tzinfo=None),
    )
    db.add(row)
    db.flush()
    return _entity_from_row(row)


def record_relationship(
    db, *, from_entity_id: str, to_entity_id: str, relation_type: str,
    provenance: Optional[dict[str, Any]] = None, valid_from: Optional[str] = None,
    valid_to: Optional[str] = None, confidence: float = 1.0, method_version: str,
) -> EntityRelationship:
    if relation_type not in RELATION_TYPES:
        raise ValueError(f"relation_type must be one of {RELATION_TYPES}, got {relation_type!r}")

    from core.db.models import EntityRelationshipDB

    now = datetime.now(timezone.utc)
    row_id = str(uuid.uuid4())
    db.add(EntityRelationshipDB(
        id=row_id, from_entity_id=from_entity_id, to_entity_id=to_entity_id,
        relation_type=relation_type, provenance=dict(provenance or {}),
        valid_from=valid_from, valid_to=valid_to, confidence=confidence,
        method_version=method_version, created_at=now.replace(tzinfo=None),
    ))
    db.flush()
    return EntityRelationship(
        id=row_id, from_entity_id=from_entity_id, to_entity_id=to_entity_id,
        relation_type=relation_type, provenance=dict(provenance or {}),
        valid_from=valid_from, valid_to=valid_to, confidence=confidence,
        method_version=method_version, created_at=now.isoformat(),
    )


def get_relationships(entity_id_: str) -> list[EntityRelationship]:
    from core.db.models import EntityRelationshipDB
    from core.db.session import session_scope

    with session_scope() as db:
        rows = (
            db.query(EntityRelationshipDB)
            .filter(
                (EntityRelationshipDB.from_entity_id == entity_id_)
                | (EntityRelationshipDB.to_entity_id == entity_id_)
            )
            .order_by(EntityRelationshipDB.created_at.desc())
            .all()
        )
        return [_relationship_from_row(r) for r in rows]


def _entity_from_row(row) -> Entity:
    return Entity(
        entity_id=row.entity_id, entity_type=row.entity_type, canonical_key=row.canonical_key,
        display_name=row.display_name, attributes=dict(row.attributes or {}),
        created_at=row.created_at.isoformat(),
    )


def _relationship_from_row(row) -> EntityRelationship:
    return EntityRelationship(
        id=row.id, from_entity_id=row.from_entity_id, to_entity_id=row.to_entity_id,
        relation_type=row.relation_type, provenance=dict(row.provenance or {}),
        valid_from=row.valid_from, valid_to=row.valid_to, confidence=row.confidence,
        method_version=row.method_version, created_at=row.created_at.isoformat(),
    )
