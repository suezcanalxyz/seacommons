# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P0.1: production Humanitarian truth-table audit.

Exit gate, verbatim: "every unexplained visible anomaly has a code/data-
path explanation and a redacted regression fixture or explicit
remediation packet."
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.intel.humanitarian_truth_table import (
    NOT_YET_COMPUTABLE,
    DriftSummary,
    build_case_row,
    compute_anomaly_flags,
)

_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def test_a_healthy_case_has_no_anomaly_flags():
    flags = compute_anomaly_flags(
        lifecycle="active",
        drifts=[DriftSummary("d1", "completed", _NOW - timedelta(hours=1))],
        marker_visible=True, drift_visible=True,
        source_status="active", now=_NOW,
    )
    assert flags == []


def test_multiple_current_drifts_is_flagged():
    flags = compute_anomaly_flags(
        lifecycle="active",
        drifts=[
            DriftSummary("d1", "completed", _NOW - timedelta(hours=1)),
            DriftSummary("d2", "completed", _NOW - timedelta(hours=2)),
        ],
        marker_visible=True, drift_visible=True,
        source_status="active", now=_NOW,
    )
    assert "MULTIPLE_CURRENT_DRIFTS" in flags


def test_drift_after_resolution_is_flagged():
    flags = compute_anomaly_flags(
        lifecycle="resolved",
        drifts=[DriftSummary("d1", "completed", _NOW - timedelta(hours=1))],
        marker_visible=False, drift_visible=True,
        source_status="active", now=_NOW,
    )
    assert "DRIFT_AFTER_RESOLUTION" in flags


def test_stale_drift_is_flagged():
    flags = compute_anomaly_flags(
        lifecycle="active",
        drifts=[DriftSummary("d1", "completed", _NOW - timedelta(hours=30))],
        marker_visible=True, drift_visible=True,
        source_status="active", now=_NOW,
    )
    assert "STALE_DRIFT" in flags


def test_a_recent_drift_is_not_stale():
    flags = compute_anomaly_flags(
        lifecycle="active",
        drifts=[DriftSummary("d1", "completed", _NOW - timedelta(hours=2))],
        marker_visible=True, drift_visible=True,
        source_status="active", now=_NOW,
    )
    assert "STALE_DRIFT" not in flags


def test_open_case_dropped_from_live_is_flagged():
    flags = compute_anomaly_flags(
        lifecycle="active", drifts=[],
        marker_visible=False, drift_visible=False,
        source_status="active", now=_NOW,
    )
    assert "OPEN_CASE_DROPPED_FROM_LIVE" in flags


def test_resolved_case_still_active_looking_is_flagged():
    flags = compute_anomaly_flags(
        lifecycle="resolved", drifts=[],
        marker_visible=True, drift_visible=False,
        source_status="active", now=_NOW,
    )
    assert "RESOLVED_CASE_STILL_ACTIVE_LOOKING" in flags


def test_archived_lifecycle_is_always_flagged_as_silence_only():
    """core.intel.lifecycle.distress_lifecycle() only ever returns
    "archived" through its age-based silence branch -- resolved/
    needs_review both return earlier -- so this flag fires by
    construction whenever lifecycle=="archived"."""
    flags = compute_anomaly_flags(
        lifecycle="archived", drifts=[],
        marker_visible=True, drift_visible=False,
        source_status="active", now=_NOW,
    )
    assert "ARCHIVED_BY_SILENCE_ONLY" in flags


def test_source_stale_or_down_is_flagged():
    for status in ("degraded", "down", "unknown"):
        flags = compute_anomaly_flags(
            lifecycle="active", drifts=[],
            marker_visible=True, drift_visible=False,
            source_status=status, now=_NOW,
        )
        assert "SOURCE_STALE_OR_DOWN" in flags, status


def test_source_active_is_not_flagged():
    flags = compute_anomaly_flags(
        lifecycle="active", drifts=[],
        marker_visible=True, drift_visible=False,
        source_status="active", now=_NOW,
    )
    assert "SOURCE_STALE_OR_DOWN" not in flags


def test_build_case_row_always_names_the_not_yet_computable_flags():
    """docs/updates.md invariant #10/#14: never silently omit what this
    module cannot answer yet -- name it and the packet that unblocks it."""
    row = build_case_row(
        event_id="e1", source="Alarm Phone", source_publication_time="2026-09-04T10:00:00Z",
        retrieved_at="2026-09-04T10:01:00Z", last_update_at="2026-09-04T10:05:00Z",
        lifecycle="active", drifts=[], marker_visible=True, drift_visible=False,
        publishable=True, source_status="active", now=_NOW,
    )
    assert set(row.unavailable_flags) == set(NOT_YET_COMPUTABLE)
    assert row.visible_feature_id == "intel:e1"
    assert row.publication_decision == "publishable"


def test_build_case_row_reports_withheld_when_not_publishable():
    row = build_case_row(
        event_id="e2", source="Alarm Phone", source_publication_time=None,
        retrieved_at=None, last_update_at=None,
        lifecycle="active", drifts=[], marker_visible=False, drift_visible=False,
        publishable=False, source_status="active", now=_NOW,
    )
    assert row.publication_decision == "withheld"


def test_multiple_completed_drifts_report_no_single_current_status():
    row = build_case_row(
        event_id="e3", source="Alarm Phone", source_publication_time=None,
        retrieved_at=None, last_update_at=None,
        lifecycle="active",
        drifts=[
            DriftSummary("d1", "completed", _NOW - timedelta(hours=1)),
            DriftSummary("d2", "completed", _NOW - timedelta(hours=2)),
        ],
        marker_visible=True, drift_visible=True,
        publishable=True, source_status="active", now=_NOW,
    )
    assert set(row.current_drift_ids) == {"d1", "d2"}
    assert row.current_drift_status is None
    assert "MULTIPLE_CURRENT_DRIFTS" in row.anomaly_flags


# ── live wiring ──────────────────────────────────────────────────────────


def test_run_humanitarian_truth_table_audit_runs_against_the_real_db():
    """docs/updates.md P0.1: the real entry point -- queries the actual
    IntelEventDB/DriftResultDB and the actual public projections, not a
    synthetic snapshot."""
    from core.intel.humanitarian_truth_table import run_humanitarian_truth_table_audit

    result = run_humanitarian_truth_table_audit(limit=50)
    assert isinstance(result["case_count"], int)
    assert isinstance(result["rows"], list)
    assert result["not_yet_computable_flags"] == NOT_YET_COMPUTABLE


def test_run_humanitarian_truth_table_audit_finds_a_real_open_case_dropped_from_live():
    """A real distress IntelEventDB row persisted directly (bypassing
    intel_store, which would make it appear in the live projection) is
    exactly the OPEN_CASE_DROPPED_FROM_LIVE scenario -- proving the audit
    reads real production tables, not intel_store's in-memory cache."""
    import uuid

    from core.intel.humanitarian_truth_table import run_humanitarian_truth_table_audit
    from core.db.models import IntelEventDB
    from core.db.session import session_scope

    event_id = f"pytest-audit-{uuid.uuid4()}"
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        db.add(IntelEventDB(
            id=event_id, timestamp_utc=now.isoformat(), type="distress", severity="high",
            lat=35.5, lon=14.1, title="Distress reported", text="Boat in distress",
            source=f"pytest-source-{uuid.uuid4()}", meta={"is_distress": True},
            created_at=now.replace(tzinfo=None), maritime_domain="sar",
        ))

    result = run_humanitarian_truth_table_audit(limit=500)
    match = next((r for r in result["rows"] if r.candidate_incident_id == event_id), None)
    assert match is not None
    assert "OPEN_CASE_DROPPED_FROM_LIVE" in match.anomaly_flags


def test_humanitarian_truth_table_route_exposes_the_real_audit() -> None:
    """docs/updates.md P0.1: the real GET /api/v1/audit/humanitarian-
    truth-table route, exercised end to end via FastAPI, not just the
    underlying function."""
    from fastapi.testclient import TestClient

    from core.api.main import app

    response = TestClient(app).get("/api/v1/audit/humanitarian-truth-table?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert "rows" in payload
    assert "not_yet_computable_flags" in payload
    assert set(payload["not_yet_computable_flags"]) == set(NOT_YET_COMPUTABLE)
