# SPDX-License-Identifier: AGPL-3.0-or-later
"""IncidentWatch v0: bounded follow-up without mutating incident truth."""
from __future__ import annotations

from sqlalchemy import UniqueConstraint


def test_incident_watch_model_has_unique_incident_and_due_index():
    from core.db.models import IncidentWatchDB

    table = IncidentWatchDB.__table__
    assert table.name == "incident_watches"
    assert {column.name for column in table.columns} >= {
        "watch_id", "incident_id", "status", "priority", "lifecycle_snapshot",
        "profile_json", "profile_version", "next_run_at", "last_run_at",
        "last_success_at", "last_error_at", "last_error_class", "consecutive_errors",
        "run_count", "query_fingerprint", "lease_owner", "lease_until",
        "created_at", "updated_at", "expires_at",
    }
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("incident_id",) in unique_columns
    index_columns = {
        tuple(column.name for column in index.columns)
        for index in table.indexes
    }
    assert ("status", "next_run_at", "priority") in index_columns

from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def watch_tables():
    from core.db.models import HumanitarianIncidentDB, IncidentWatchDB, IntelEventDB
    from core.db.session import engine, session_scope

    for table in (IntelEventDB.__table__, HumanitarianIncidentDB.__table__, IncidentWatchDB.__table__):
        table.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(IncidentWatchDB).delete()
        db.query(HumanitarianIncidentDB).delete()
        db.query(IntelEventDB).delete()
    yield


def test_active_policy_is_highest_priority_and_fifteen_minutes():
    from core.intel.incident_watch import policy_for_state

    policy = policy_for_state(
        incident_status="active", lifecycle="active", resolved_at=None, now=NOW,
    )
    assert policy.status == "active"
    assert policy.priority == "highest"
    assert policy.cadence == timedelta(minutes=15)


def test_needs_review_policy_is_high_and_thirty_minutes():
    from core.intel.incident_watch import policy_for_state

    policy = policy_for_state(
        incident_status="needs_review", lifecycle="needs_review", resolved_at=None, now=NOW,
    )
    assert policy.status == "active"
    assert policy.priority == "high"
    assert policy.cadence == timedelta(minutes=30)


def test_outcome_unknown_legacy_archived_keeps_followup():
    from core.intel.incident_watch import policy_for_state

    policy = policy_for_state(
        incident_status="outcome_unknown", lifecycle="archived", resolved_at=None, now=NOW,
    )
    assert policy.status == "active"
    assert policy.priority == "medium"
    assert policy.cadence == timedelta(hours=2)


def test_resolved_older_than_thirty_days_expires():
    from core.intel.incident_watch import policy_for_state

    policy = policy_for_state(
        incident_status="resolved", lifecycle="resolved",
        resolved_at=NOW - timedelta(days=31), now=NOW,
    )
    assert policy.status == "expired"
    assert policy.cadence is None


def test_plain_archived_case_expires_without_polling():
    from core.intel.incident_watch import policy_for_state

    policy = policy_for_state(
        incident_status="archived", lifecycle="archived", resolved_at=None, now=NOW,
    )
    assert policy.status == "expired"
    assert policy.cadence is None


def test_profile_uses_only_explicit_persisted_evidence(watch_tables):
    from core.db.models import HumanitarianIncidentDB, IntelEventDB
    from core.db.session import session_scope
    from core.intel.incident_watch import build_watch_profile

    with session_scope() as db:
        db.add(IntelEventDB(
            id="iw-profile", timestamp_utc="2026-09-05T10:00:00+00:00",
            type="twitter", severity="high", lat=34.5, lon=13.2,
            title="MAYDAY 40 people aboard", text="route unknown", url="https://x.com/a/status/123",
            source="Alarm Phone", linked_mmsi="", meta={"tweet_id": "123", "is_distress": True},
            location_uncertainty_m=5000,
        ))
        incident = HumanitarianIncidentDB(
            incident_id="iw-profile", lifecycle="active", incident_status="active",
            case_type="distress", reported_at="2026-09-05T10:00:00+00:00",
            last_update_at="2026-09-05T10:00:00+00:00",
            source_observation_ids=["obs-explicit"], review_status="none", revision=1,
        )
        db.add(incident)
        db.flush()
        profile = build_watch_profile(db, incident)

    assert profile["incident_id"] == "iw-profile"
    assert profile["source_item_ids"] == ["123"]
    assert profile["source_names"] == ["Alarm Phone"]
    assert profile["coordinates"] == [{"lat": 34.5, "lon": 13.2, "uncertainty_m": 5000.0}]
    assert profile["source_observation_ids"] == ["obs-explicit"]
    assert profile["route_terms"] == []
    assert profile["vessel_description_terms"] == []
    assert "linked_mmsi" not in profile
    assert "mmsi" not in profile


def test_sync_watch_is_idempotent_one_row_per_incident(watch_tables):
    from core.db.models import HumanitarianIncidentDB
    from core.db.session import session_scope
    from core.intel.incident_watch import get_watch, sync_watch_for_incident

    with session_scope() as db:
        db.add(HumanitarianIncidentDB(
            incident_id="iw-sync", lifecycle="active", incident_status="active",
            case_type="distress", reported_at="2026-09-05T10:00:00+00:00",
            last_update_at="2026-09-05T10:00:00+00:00",
            source_observation_ids=[], review_status="none", revision=1,
        ))
    first = sync_watch_for_incident("iw-sync", now=NOW)
    second = sync_watch_for_incident("iw-sync", now=NOW + timedelta(minutes=1))
    assert first is not None and second is not None
    assert first["watch_id"] == second["watch_id"]

    from core.db.models import IncidentWatchDB
    with session_scope() as db:
        assert db.query(IncidentWatchDB).filter_by(incident_id="iw-sync").count() == 1
    watch = get_watch("iw-sync")
    assert watch["priority"] == "highest"
    assert watch["status"] == "active"


def test_canonical_incident_sync_also_syncs_watch_after_commit(watch_tables):
    from core.intel.humanitarian_incident import sync_incident_for_event
    from core.intel.incident_watch import get_watch
    from core.intel.store import IntelEvent

    event = IntelEvent(
        id="iw-humanitarian-sync", type="distress", severity="high",
        lat=35.5, lon=14.1, title="MAYDAY", text="urgent rescue needed",
        source="Alarm Phone", timestamp_utc="2026-09-05T11:00:00+00:00",
        metadata={"is_distress": True, "tweet_id": "9001"},
    )
    sync_incident_for_event(event, lifecycle="active", case_type="distress")
    watch = get_watch("iw-humanitarian-sync")
    assert watch is not None
    assert watch["profile_json"]["source_item_ids"] == ["9001"]
