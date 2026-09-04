# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P2.3: Entity graph.

Exit gate (v0-bounded, per module docstring): get_or_create_entity is
idempotent by (entity_type, canonical_key); record_observation
mechanically wires a real reported_by edge; circular_reporting's
derived_from detection projects into the same graph.
"""
from __future__ import annotations

import uuid

import pytest

from core.intel.entity_graph import (
    ENTITY_TYPES,
    NOT_YET_WIRED,
    RELATION_TYPES,
    entity_id,
    get_or_create_entity,
    get_relationships,
    record_relationship,
)
from core.intel.source_observation import record_observation


@pytest.fixture(autouse=True)
def _fresh_tables():
    from core.db.models import (
        EntityDB,
        EntityRelationshipDB,
        LineageEdgeDB,
        SourceObservationDB,
    )
    from core.db.session import engine, session_scope

    SourceObservationDB.__table__.create(bind=engine(), checkfirst=True)
    LineageEdgeDB.__table__.create(bind=engine(), checkfirst=True)
    EntityDB.__table__.create(bind=engine(), checkfirst=True)
    EntityRelationshipDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(SourceObservationDB).delete()
        db.query(LineageEdgeDB).delete()
        db.query(EntityDB).delete()
        db.query(EntityRelationshipDB).delete()
    yield


def test_entity_id_is_deterministic():
    assert entity_id("vessel", "mmsi:123") == entity_id("vessel", "mmsi:123")
    assert entity_id("vessel", "mmsi:123") != entity_id("port", "mmsi:123")


def test_get_or_create_entity_is_idempotent():
    from core.db.session import session_scope

    with session_scope() as db:
        first = get_or_create_entity(db, entity_type="source_account", canonical_key="Alarm Phone")
        second = get_or_create_entity(db, entity_type="source_account", canonical_key="Alarm Phone")
    assert first.entity_id == second.entity_id


def test_get_or_create_entity_rejects_an_unknown_type():
    from core.db.session import session_scope

    with session_scope() as db:
        with pytest.raises(ValueError):
            get_or_create_entity(db, entity_type="spaceship", canonical_key="x")


def test_record_relationship_rejects_an_unknown_relation_type():
    from core.db.session import session_scope

    with session_scope() as db:
        a = get_or_create_entity(db, entity_type="vessel", canonical_key="mmsi:1")
        b = get_or_create_entity(db, entity_type="port", canonical_key="port:1")
        with pytest.raises(ValueError):
            record_relationship(
                db, from_entity_id=a.entity_id, to_entity_id=b.entity_id,
                relation_type="teleported_to", method_version="v0",
            )


def test_record_observation_mechanically_creates_a_reported_by_edge():
    from core.db.session import session_scope

    with session_scope() as db:
        obs = record_observation(
            db, service="maritime", lane="live", observation_type="source_post",
            source_name="Test Source", source_policy="official_api",
            source_id=f"pytest-{uuid.uuid4()}", observed_at="2026-09-04T10:00:00+00:00",
            raw_payload=f"text {uuid.uuid4()}",
        )

    obs_entity_id = entity_id("observation", obs.observation_id)
    relationships = get_relationships(obs_entity_id)
    reported_by = [r for r in relationships if r.relation_type == "reported_by"]
    assert len(reported_by) == 1
    assert reported_by[0].from_entity_id == obs_entity_id
    assert reported_by[0].to_entity_id == entity_id("source_account", "Test Source")


def test_lineage_detection_projects_a_derived_from_edge_into_the_graph():
    from core.db.session import session_scope

    shared_text = f"entity graph lineage test {uuid.uuid4()}"
    with session_scope() as db:
        first = record_observation(
            db, service="maritime", lane="live", observation_type="source_post",
            source_name="Wire Service", source_policy="official_api",
            source_id=f"pytest-{uuid.uuid4()}", observed_at="2026-09-04T08:00:00+00:00",
            raw_payload=shared_text,
        )
    with session_scope() as db:
        second = record_observation(
            db, service="maritime", lane="live", observation_type="source_post",
            source_name="Local News", source_policy="official_api",
            source_id=f"pytest-{uuid.uuid4()}", observed_at="2026-09-04T09:00:00+00:00",
            raw_payload=shared_text,
        )

    second_entity_id = entity_id("observation", second.observation_id)
    relationships = get_relationships(second_entity_id)
    derived = [r for r in relationships if r.relation_type == "derived_from"]
    assert len(derived) == 1
    assert derived[0].to_entity_id == entity_id("observation", first.observation_id)


def test_not_yet_wired_types_are_named():
    assert "vessel" in NOT_YET_WIRED
    assert "corroborates" in NOT_YET_WIRED


def test_entity_graph_route_exposes_real_relationships() -> None:
    from fastapi.testclient import TestClient

    from core.api.main import app
    from core.db.session import session_scope

    with session_scope() as db:
        record_observation(
            db, service="maritime", lane="live", observation_type="source_post",
            source_name="Route Test Source", source_policy="official_api",
            source_id=f"pytest-{uuid.uuid4()}", observed_at="2026-09-04T10:00:00+00:00",
            raw_payload=f"text {uuid.uuid4()}",
        )

    response = TestClient(app).get("/api/v1/audit/entity-graph/source_account/Route Test Source")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["relationships"]) == 1
    assert payload["relationships"][0]["relation_type"] == "reported_by"
