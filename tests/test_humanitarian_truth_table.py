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


def test_truth_table_keeps_recent_resolved_cases_in_audit():
    """A resolved report remains auditable for a lingering published drift."""
    import uuid

    from core.db.models import IntelEventDB
    from core.db.session import session_scope
    from core.intel.humanitarian_truth_table import run_humanitarian_truth_table_audit

    event_id = f"pytest-resolved-audit-{uuid.uuid4()}"
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        db.add(IntelEventDB(
            id=event_id, timestamp_utc=now.isoformat(), type="distress", severity="low",
            lat=35.5, lon=14.1, title="Rescue completed",
            text="All 47 people aboard the Zenobia near Lampedusa were rescued and are now safe.",
            source=f"pytest-resolved-source-{uuid.uuid4()}",
            meta={"is_distress": True},
            created_at=now.replace(tzinfo=None), maritime_domain="sar",
        ))

    result = run_humanitarian_truth_table_audit(limit=500)
    match = next((row for row in result["rows"] if row.candidate_incident_id == event_id), None)
    assert match is not None, "Recent resolved cases must not disappear before anomaly checks"
    assert match.lifecycle == "resolved"


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
    assert payload["live_visible_feature_count"] >= 0
    assert (
        payload["live_visible_features_with_audit_row_count"]
        + payload["live_visible_features_without_audit_row_count"]
        == payload["live_visible_feature_count"]
    )


def test_recent_completed_drift_does_not_inherit_staleness_from_older_one():
    """An older completed result cannot make a fresh update look stale."""
    flags = compute_anomaly_flags(
        lifecycle="active",
        drifts=[
            DriftSummary("old", "completed", _NOW - timedelta(hours=30)),
            DriftSummary("new", "completed", _NOW - timedelta(hours=1)),
        ],
        marker_visible=True, drift_visible=True,
        source_status="active", now=_NOW,
    )
    assert "MULTIPLE_CURRENT_DRIFTS" in flags
    assert "STALE_DRIFT" not in flags


def test_all_completed_drifts_stale_remains_flagged():
    """Old-only results still require a fresh drift estimate."""
    flags = compute_anomaly_flags(
        lifecycle="active",
        drifts=[
            DriftSummary("old-1", "completed", _NOW - timedelta(hours=30)),
            DriftSummary("old-2", "completed", _NOW - timedelta(hours=26)),
        ],
        marker_visible=True, drift_visible=True,
        source_status="active", now=_NOW,
    )
    assert "MULTIPLE_CURRENT_DRIFTS" in flags
    assert "STALE_DRIFT" in flags


def test_batch_drift_index_matches_raw_and_prefixed_event_ids():
    """One bounded drift query must preserve both persisted event-id forms."""
    from types import SimpleNamespace
    from core.intel.humanitarian_truth_table import index_drift_summaries

    rows = [
        SimpleNamespace(event_id="e1", drift_id="d1", status="completed", created_at=_NOW),
        SimpleNamespace(event_id="intel:e1", drift_id="d2", status="completed", created_at=_NOW),
        SimpleNamespace(event_id="e2", drift_id="d3", status="pending", created_at=None),
        SimpleNamespace(event_id="unrelated", drift_id="d4", status="completed", created_at=_NOW),
    ]
    indexed = index_drift_summaries(["e1", "e2"], rows)
    assert [d.drift_id for d in indexed["e1"]] == ["d1", "d2"]
    assert [d.drift_id for d in indexed["e2"]] == ["d3"]
    assert all(d.drift_id != "d4" for items in indexed.values() for d in items)


def test_batch_drift_index_handles_overlapping_prefixed_case_ids():
    """An alias shared by two case identifiers must not drop either audit row."""
    from types import SimpleNamespace
    from core.intel.humanitarian_truth_table import index_drift_summaries

    row = SimpleNamespace(
        event_id="intel:e1", drift_id="d1", status=None, created_at=None,
    )
    indexed = index_drift_summaries(["e1", "intel:e1"], [row])
    assert [d.drift_id for d in indexed["e1"]] == ["d1"]
    assert [d.drift_id for d in indexed["intel:e1"]] == ["d1"]
    assert indexed["e1"][0].status == "unknown"


def test_batch_drift_index_empty_case_set():
    from core.intel.humanitarian_truth_table import index_drift_summaries
    assert index_drift_summaries([], []) == {}


def test_audit_followup_preserves_source_for_resolution_and_rejects_other_sources():
    """A DB follow-up must retain its source or the lifecycle resolver ignores it."""
    from types import SimpleNamespace

    from core.intel.humanitarian_truth_table import _audit_followup_event
    from core.intel.lifecycle import distress_lifecycle, has_resolution_signal
    from core.intel.store import IntelEvent

    original = IntelEvent(
        id="boat01", type="twitter", source="Alarm Phone",
        text="🆘 47 people in distress aboard the vessel Zenobia near Lampedusa.",
        timestamp_utc="2026-07-29T05:00:00+00:00",
    )
    row = SimpleNamespace(
        id="boat01-followup", source="Alarm Phone",
        timestamp_utc="2026-07-29T09:00:00+00:00",
        title="Alarm Phone update",
        text="Update: all 47 people aboard the Zenobia near Lampedusa were rescued and are now safe.",
        meta={},
    )
    followup = _audit_followup_event(row)
    now = datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc)
    assert followup.source == original.source
    assert has_resolution_signal(original, [followup], now=now)
    assert distress_lifecycle(original, now=now, same_source=[followup]) == "resolved"

    # A similarly worded report from a different NGO is not case closure.
    other_source = _audit_followup_event(SimpleNamespace(**{
        **vars(row), "source": "Sea-Watch",
    }))
    assert not has_resolution_signal(original, [other_source], now=now)
    assert distress_lifecycle(original, now=now, same_source=[other_source]) == "active"


def test_source_followup_fetch_limit_scales_with_case_count_and_stays_bounded():
    from core.intel.humanitarian_truth_table import source_followup_fetch_limit

    assert source_followup_fetch_limit(0) == 0
    assert source_followup_fetch_limit(1) == 51
    assert source_followup_fetch_limit(2) == 102
    assert source_followup_fetch_limit(200) == 5000


def test_humanitarian_audit_overscans_unrelated_recent_news():
    """A busy news feed must not hide a recent distress beyond limit(N)."""
    import uuid

    from core.db.models import IntelEventDB
    from core.db.session import session_scope
    from core.intel.humanitarian_truth_table import run_humanitarian_truth_table_audit

    now = datetime.now(timezone.utc)
    token = uuid.uuid4().hex[:12]
    case_id = f"pytest-audit-overscan-{token}"
    with session_scope() as db:
        db.add(IntelEventDB(
            id=case_id, timestamp_utc=now.isoformat(), type="distress", severity="high",
            lat=35.5, lon=14.1, title="Distress reported", text="Boat in distress",
            source=f"pytest-overscan-{token}", meta={"is_distress": True},
            created_at=(now - timedelta(seconds=1)).replace(tzinfo=None),
            maritime_domain="sar",
        ))
        for i in range(55):
            db.add(IntelEventDB(
                id=f"pytest-news-{token}-{i}", timestamp_utc=now.isoformat(),
                type="news", severity="low", title="Unrelated market report",
                text="Unrelated market report", source=f"pytest-news-{token}",
                meta={"service": "maritime", "lane": "intelligence"},
                created_at=now.replace(tzinfo=None), maritime_domain="grey_zone",
            ))

    result = run_humanitarian_truth_table_audit(limit=50)
    assert result["audited_source_rows_count"] >= 56
    assert any(row.candidate_incident_id == case_id for row in result["rows"])
    assert isinstance(result["audit_scan_truncated"], bool)
    assert isinstance(result["followup_coverage_incomplete_source_count"], int)


def test_same_source_followup_batch_filters_source_self_and_lookback():
    from types import SimpleNamespace
    from core.intel.humanitarian_truth_table import index_recent_same_source_followups

    def item(id, source, days):
        return SimpleNamespace(
            id=id, source=source, created_at=_NOW.replace(tzinfo=None) + timedelta(days=days),
        )

    case = item("distress", "Alarm Phone", 0)
    rows = [
        item("future-followup", "Alarm Phone", 1),
        item("old", "Alarm Phone", -15),
        item("other-source", "Sea Watch", 1),
        case,
        item("boundary", "Alarm Phone", -14),
    ]
    matched = index_recent_same_source_followups([case], rows)
    assert [r.id for r in matched["distress"]] == ["future-followup", "boundary"]


def test_same_source_followup_batch_retains_latest_50_without_current_case():
    from types import SimpleNamespace
    from core.intel.humanitarian_truth_table import index_recent_same_source_followups

    now = _NOW.replace(tzinfo=None)
    case = SimpleNamespace(id="case", source="Alarm Phone", created_at=now)
    rows = [
        SimpleNamespace(
            id=f"followup-{i:02d}", source="Alarm Phone",
            created_at=now + timedelta(minutes=i + 1),
        )
        for i in range(60)
    ]
    rows.append(case)
    matched = index_recent_same_source_followups([case], rows)
    assert len(matched["case"]) == 50
    assert matched["case"][0].id == "followup-59"
    assert matched["case"][-1].id == "followup-10"


def test_same_source_followup_batch_handles_multiple_cases_and_no_rows():
    from types import SimpleNamespace
    from core.intel.humanitarian_truth_table import index_recent_same_source_followups

    now = _NOW.replace(tzinfo=None)
    cases = [
        SimpleNamespace(id="a", source="A", created_at=now),
        SimpleNamespace(id="b", source="B", created_at=now),
    ]
    source_rows = [
        SimpleNamespace(id="followup-a", source="A", created_at=now + timedelta(hours=1)),
        SimpleNamespace(id="followup-b", source="B", created_at=now + timedelta(hours=2)),
    ]
    result = index_recent_same_source_followups(cases, source_rows)
    assert [row.id for row in result["a"]] == ["followup-a"]
    assert [row.id for row in result["b"]] == ["followup-b"]
    assert index_recent_same_source_followups([], []) == {}


def test_same_source_followup_batch_exposes_51st_candidate_for_audit():
    """A 50-post lifecycle window cannot certify a 51st same-source update."""
    from types import SimpleNamespace
    from core.intel.humanitarian_truth_table import index_recent_same_source_followups

    now = _NOW.replace(tzinfo=None)
    case = SimpleNamespace(id="case-cap", source="Alarm Phone", created_at=now)
    posts = [
        SimpleNamespace(
            id=f"cap-{i}", source="Alarm Phone",
            created_at=now + timedelta(minutes=i + 1),
        )
        for i in range(51)
    ]
    assert len(index_recent_same_source_followups([case], posts)["case-cap"]) == 50
    assert len(index_recent_same_source_followups(
        [case], posts, max_per_case=51,
    )["case-cap"]) == 51


def test_humanitarian_audit_reports_per_case_followup_candidate_truncation():
    """Source-level truncation alone does not identify affected case windows."""
    import uuid

    from core.db.models import IntelEventDB
    from core.db.session import session_scope
    from core.intel.humanitarian_truth_table import run_humanitarian_truth_table_audit

    now = datetime.now(timezone.utc)
    token = uuid.uuid4().hex[:12]
    source = f"pytest-followup-cap-{token}"
    case_id = f"pytest-cap-case-{token}"
    with session_scope() as db:
        db.add(IntelEventDB(
            id=case_id, timestamp_utc=(now - timedelta(minutes=2)).isoformat(),
            type="distress", severity="high", lat=35.5, lon=14.1,
            title="Distress reported", text="Boat in distress",
            source=source, meta={"is_distress": True},
            created_at=(now - timedelta(minutes=2)).replace(tzinfo=None),
            maritime_domain="sar",
        ))
        for i in range(60):
            db.add(IntelEventDB(
                id=f"pytest-cap-news-{token}-{i}",
                timestamp_utc=(now - timedelta(minutes=1, seconds=59-i)).isoformat(),
                type="news", severity="low", title="Unrelated report",
                text="Unrelated report", source=source,
                meta={"service": "maritime", "lane": "intelligence"},
                created_at=(now - timedelta(seconds=60-i)).replace(tzinfo=None),
                maritime_domain="grey_zone",
            ))

    result = run_humanitarian_truth_table_audit(limit=50)
    assert any(row.candidate_incident_id == case_id for row in result["rows"])
    assert result["followup_candidate_window_truncated_case_count"] >= 1
    assert result["followup_coverage_incomplete_source_count"] >= 1


def test_visible_live_humanitarian_coverage_counts_unmatched_features():
    """A Live/audit discrepancy must be measurable without exposing IDs."""
    from core.intel.humanitarian_truth_table import summarize_visible_case_coverage

    counts = summarize_visible_case_coverage(
        {"intel:case-a", "case-b", "intel:case-c", "intel:case-c"},
        ["case-a", "case-c", "case-not-live"],
    )
    assert counts == {
        "live_visible_feature_count": 3,
        "live_visible_features_with_audit_row_count": 2,
        "live_visible_features_without_audit_row_count": 1,
    }


def test_visible_live_humanitarian_coverage_handles_empty_and_prefix_ids():
    from core.intel.humanitarian_truth_table import summarize_visible_case_coverage

    assert summarize_visible_case_coverage({"intel:", "", "intel:x"}, ["x"]) == {
        "live_visible_feature_count": 1,
        "live_visible_features_with_audit_row_count": 1,
        "live_visible_features_without_audit_row_count": 0,
    }
    assert summarize_visible_case_coverage(set(), []) == {
        "live_visible_feature_count": 0,
        "live_visible_features_with_audit_row_count": 0,
        "live_visible_features_without_audit_row_count": 0,
    }
