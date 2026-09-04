# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md Section 6: Preservation and evidentiary provenance.

Exit gate (v0-bounded, per module docstring): preservation_status is
computed once at record_observation() time and never changes on
replay; Humanitarian material is always segregated into "restricted"
regardless of archive-ref presence.
"""
from __future__ import annotations

import uuid

import pytest

from core.db.session import session_scope
from core.intel.preservation import (
    STATUS_NOT_APPLICABLE,
    STATUS_PRESERVED,
    STATUS_RESTRICTED,
    classify_preservation_status,
    summarize_preservation_status,
)
from core.intel.source_observation import record_observation


@pytest.fixture(autouse=True)
def _fresh_table():
    from core.db.models import SourceObservationDB
    from core.db.session import engine

    SourceObservationDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(SourceObservationDB).delete()
    yield


def test_no_archive_ref_is_not_applicable_regardless_of_service():
    assert classify_preservation_status("maritime", has_archive_ref=False) == STATUS_NOT_APPLICABLE
    assert classify_preservation_status("humanitarian", has_archive_ref=False) == STATUS_NOT_APPLICABLE


def test_humanitarian_with_archive_ref_is_always_restricted():
    """docs/updates.md Section 6: "segregate restricted artifacts" --
    enforced structurally, not left to a caller's discretion."""
    assert classify_preservation_status("humanitarian", has_archive_ref=True) == STATUS_RESTRICTED


def test_non_humanitarian_with_archive_ref_is_preserved():
    assert classify_preservation_status("maritime", has_archive_ref=True) == STATUS_PRESERVED


def test_record_observation_stores_the_computed_status():
    with session_scope() as db:
        obs = record_observation(
            db, service="humanitarian", lane="review", observation_type="source_post",
            source_name="pytest-source", source_policy="official_api",
            source_id=f"pytest-{uuid.uuid4()}", observed_at="2026-09-04T10:00:00+00:00",
            raw_payload="test", raw_payload_ref="archive://pytest/1",
        )
    assert obs.preservation_status == STATUS_RESTRICTED


def test_record_observation_with_no_ref_is_not_applicable():
    with session_scope() as db:
        obs = record_observation(
            db, service="maritime", lane="live", observation_type="source_post",
            source_name="pytest-source", source_policy="official_api",
            source_id=f"pytest-{uuid.uuid4()}", observed_at="2026-09-04T10:00:00+00:00",
            raw_payload="test",
        )
    assert obs.preservation_status == STATUS_NOT_APPLICABLE


def test_replaying_the_same_observation_never_changes_its_status():
    source_id = f"pytest-{uuid.uuid4()}"
    with session_scope() as db:
        first = record_observation(
            db, service="humanitarian", lane="review", observation_type="source_post",
            source_name="pytest-source", source_policy="official_api", source_id=source_id,
            observed_at="2026-09-04T10:00:00+00:00", raw_payload="test",
            raw_payload_ref="archive://pytest/2",
        )
        second = record_observation(
            db, service="maritime", lane="live", observation_type="source_post",
            source_name="pytest-source", source_policy="official_api", source_id=source_id,
            observed_at="2026-09-04T10:00:00+00:00", raw_payload="test",
        )
    assert first.preservation_status == STATUS_RESTRICTED
    assert second.preservation_status == STATUS_RESTRICTED  # unchanged -- replayed, not re-classified
    assert second.replayed is True


def test_summarize_preservation_status_counts_real_rows():
    with session_scope() as db:
        record_observation(
            db, service="humanitarian", lane="review", observation_type="source_post",
            source_name="pytest-summary", source_policy="official_api",
            source_id=f"pytest-{uuid.uuid4()}", observed_at="2026-09-04T10:00:00+00:00",
            raw_payload="test", raw_payload_ref="archive://pytest/3",
        )
    counts = summarize_preservation_status()
    assert counts[STATUS_RESTRICTED] >= 1


def test_preservation_summary_route_exposes_the_real_counts() -> None:
    from fastapi.testclient import TestClient

    from core.api.main import app

    response = TestClient(app).get("/api/v1/audit/preservation-summary")
    assert response.status_code == 200
    payload = response.json()
    assert STATUS_NOT_APPLICABLE in payload["counts"]
