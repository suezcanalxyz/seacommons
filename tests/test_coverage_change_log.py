# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P1.3: Coverage-change integrity.

Exit gate (v0-bounded, per module docstring): every coverage-change
event is appended (never edited/collapsed), profile_version increments
per source, unique-event yield and historical availability are real
DB-derived numbers, and duplicate/correlation yield + backfill status
are named as not-yet-computable rather than fabricated.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from core.db.models import IntelEventDB
from core.db.session import session_scope
from core.intel.coverage_change_log import (
    NOT_YET_COMPUTABLE,
    compute_unique_event_yield,
    get_coverage_change_log,
    historical_availability,
    record_coverage_change,
)


@pytest.fixture(autouse=True)
def _fresh_table():
    from core.db.models import SourceCoverageEventDB
    from core.db.session import engine

    SourceCoverageEventDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(SourceCoverageEventDB).delete()
    yield


def test_record_coverage_change_rejects_an_unknown_event_type():
    with pytest.raises(ValueError):
        record_coverage_change("Some Source", "renamed")


def test_first_recorded_change_for_a_source_is_profile_version_one():
    event = record_coverage_change("Test Source A", "added", rationale="pilot onboarding")
    assert event.profile_version == 1
    assert event.event_type == "added"
    assert event.rationale == "pilot onboarding"


def test_profile_version_increments_per_source_never_reused():
    record_coverage_change("Test Source B", "added")
    record_coverage_change("Test Source B", "method_changed", rationale="switched RSS feed URL")
    third = record_coverage_change("Test Source B", "coverage_break", rationale="feed offline")
    assert third.profile_version == 3


def test_different_sources_version_independently():
    record_coverage_change("Test Source C", "added")
    first_for_d = record_coverage_change("Test Source D", "added")
    assert first_for_d.profile_version == 1


def test_get_coverage_change_log_filters_by_source():
    record_coverage_change("Test Source E", "added")
    record_coverage_change("Test Source F", "added")
    log = get_coverage_change_log(source_name="Test Source E")
    assert all(e.source_name == "Test Source E" for e in log)
    assert len(log) == 1


def test_a_prior_entry_is_never_edited_by_a_later_one():
    """docs/updates.md P1.3: append-only -- the version history itself
    is the audit trail."""
    first = record_coverage_change("Test Source G", "added", rationale="initial")
    record_coverage_change("Test Source G", "method_changed", rationale="new endpoint")
    log = get_coverage_change_log(source_name="Test Source G")
    original = next(e for e in log if e.profile_version == 1)
    assert original.id == first.id
    assert original.rationale == "initial"


def test_compute_unique_event_yield_counts_real_persisted_rows():
    source = f"pytest-yield-{uuid.uuid4()}"
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        for _ in range(3):
            db.add(IntelEventDB(
                id=f"pytest-{uuid.uuid4()}", timestamp_utc=now.isoformat(), type="distress",
                severity="high", lat=35.0, lon=15.0, title="t", text="t", source=source,
                created_at=now.replace(tzinfo=None),
            ))
    assert compute_unique_event_yield(source, hours=24) == 3


def test_historical_availability_returns_none_for_a_source_never_seen():
    assert historical_availability(f"pytest-never-{uuid.uuid4()}") is None


def test_historical_availability_returns_the_earliest_timestamp():
    source = f"pytest-history-{uuid.uuid4()}"
    with session_scope() as db:
        db.add(IntelEventDB(
            id=f"pytest-{uuid.uuid4()}", timestamp_utc="2026-01-01T00:00:00+00:00",
            type="distress", severity="high", lat=35.0, lon=15.0, title="t", text="t",
            source=source, created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        db.add(IntelEventDB(
            id=f"pytest-{uuid.uuid4()}", timestamp_utc="2026-06-01T00:00:00+00:00",
            type="distress", severity="high", lat=35.0, lon=15.0, title="t", text="t",
            source=source, created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
    assert historical_availability(source) == "2026-01-01T00:00:00+00:00"


def test_not_yet_computable_dimensions_are_named():
    assert "duplicate_correlation_yield" in NOT_YET_COMPUTABLE
    assert "backfill_status" in NOT_YET_COMPUTABLE


def test_coverage_change_log_route_exposes_the_real_log() -> None:
    from fastapi.testclient import TestClient

    from core.api.main import app

    record_coverage_change("Test Source Route", "added", rationale="route smoke test")
    response = TestClient(app).get("/api/v1/audit/coverage-change-log?source_name=Test Source Route")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["events"]) == 1
    assert payload["events"][0]["event_type"] == "added"
