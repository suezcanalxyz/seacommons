# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P2.2: Circular-reporting lineage.

Exit gate (v0-bounded, per module docstring): an exact cross-source
payload-hash match is detected and linked to the earliest matching
observation; count_independent_sources collapses a derived set to its
real independent-source count, not a raw URL/observation count.
"""
from __future__ import annotations

import uuid

import pytest

from core.intel.circular_reporting import (
    NOT_YET_COMPUTABLE,
    count_independent_sources,
    detect_lineage_for_observation,
    get_lineage,
)
from core.intel.source_observation import record_observation


@pytest.fixture(autouse=True)
def _fresh_tables():
    from core.db.models import LineageEdgeDB, SourceObservationDB
    from core.db.session import engine, session_scope

    SourceObservationDB.__table__.create(bind=engine(), checkfirst=True)
    LineageEdgeDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(SourceObservationDB).delete()
        db.query(LineageEdgeDB).delete()
    yield


def _record(source_name, source_id, text, observed_at):
    from core.db.session import session_scope

    with session_scope() as db:
        return record_observation(
            db, service="maritime", lane="live", observation_type="source_post",
            source_name=source_name, source_policy="official_api", source_id=source_id,
            observed_at=observed_at, raw_payload=text,
        )


def test_no_match_produces_no_lineage_edge():
    obs = _record("Source A", f"pytest-{uuid.uuid4()}", f"unique text {uuid.uuid4()}", "2026-09-04T08:00:00+00:00")
    assert get_lineage(obs.observation_id) == []


def test_identical_payload_from_a_different_source_is_linked_to_the_earlier_one():
    shared_text = f"breaking: boat in distress {uuid.uuid4()}"
    first = _record("Wire Service", f"pytest-{uuid.uuid4()}", shared_text, "2026-09-04T08:00:00+00:00")
    second = _record("Local News", f"pytest-{uuid.uuid4()}", shared_text, "2026-09-04T09:00:00+00:00")

    edges = get_lineage(second.observation_id)
    assert len(edges) == 1
    assert edges[0].to_observation_id == first.observation_id
    assert edges[0].relation == "derived_from"


def test_identical_payload_from_the_same_source_is_not_linked():
    """Two observations from the same source with the same content are
    not a republication signal -- just the same outlet, not corroborating
    lineage."""
    shared_text = f"same outlet text {uuid.uuid4()}"
    _record("Wire Service", f"pytest-{uuid.uuid4()}", shared_text, "2026-09-04T08:00:00+00:00")
    second = _record("Wire Service", f"pytest-{uuid.uuid4()}", shared_text, "2026-09-04T09:00:00+00:00")

    assert get_lineage(second.observation_id) == []


def test_a_later_observation_never_links_to_a_later_one():
    shared_text = f"chronological text {uuid.uuid4()}"
    later = _record("Outlet B", f"pytest-{uuid.uuid4()}", shared_text, "2026-09-04T10:00:00+00:00")
    earlier = _record("Outlet A", f"pytest-{uuid.uuid4()}", shared_text, "2026-09-04T08:00:00+00:00")

    # 'later' was recorded first here but its observed content matches
    # 'earlier' which was recorded second -- detection runs at record time,
    # so 'later' (recorded before 'earlier' existed) has no edge yet.
    assert get_lineage(later.observation_id) == []


def test_count_independent_sources_collapses_a_derived_pair():
    shared_text = f"count test {uuid.uuid4()}"
    first = _record("Wire Service", f"pytest-{uuid.uuid4()}", shared_text, "2026-09-04T08:00:00+00:00")
    second = _record("Local News", f"pytest-{uuid.uuid4()}", shared_text, "2026-09-04T09:00:00+00:00")

    count = count_independent_sources([first.observation_id, second.observation_id])
    assert count == 1


def test_count_independent_sources_with_no_lineage_counts_each_separately():
    a = _record("Source A", f"pytest-{uuid.uuid4()}", f"text a {uuid.uuid4()}", "2026-09-04T08:00:00+00:00")
    b = _record("Source B", f"pytest-{uuid.uuid4()}", f"text b {uuid.uuid4()}", "2026-09-04T08:00:00+00:00")

    count = count_independent_sources([a.observation_id, b.observation_id])
    assert count == 2


def test_count_independent_sources_empty_input():
    assert count_independent_sources([]) == 0


def test_not_yet_computable_signals_are_named():
    assert "quotation_relation" in NOT_YET_COMPUTABLE


def test_lineage_route_exposes_the_real_edges() -> None:
    from fastapi.testclient import TestClient

    from core.api.main import app

    shared_text = f"route test {uuid.uuid4()}"
    first = _record("Wire Service", f"pytest-{uuid.uuid4()}", shared_text, "2026-09-04T08:00:00+00:00")
    second = _record("Local News", f"pytest-{uuid.uuid4()}", shared_text, "2026-09-04T09:00:00+00:00")

    response = TestClient(app).get(f"/api/v1/audit/lineage/{second.observation_id}")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["edges"]) == 1
    assert payload["edges"][0]["to_observation_id"] == first.observation_id
