# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M11: analyst data-health summary.

Exit gate, verbatim: "controlled source outage, stuck Drift job and
edge failure are all observable without inspecting the database
manually."
"""
from __future__ import annotations

import uuid

from core.observability_health import (
    SourceHealthSnapshot,
    build_data_health_summary,
    gather_data_health_summary,
)

_HEALTHY_SOURCE = SourceHealthSnapshot(name="alarm_phone", status="healthy", events_last_hour=5)
_EMPTY_DRIFT_REPORT = {"scanned": 0, "stuck": 0, "invalid": 0, "fixed": 0}


def test_everything_healthy_reports_healthy_true():
    summary = build_data_health_summary(
        source_snapshots=[_HEALTHY_SOURCE],
        drift_maintenance_report=_EMPTY_DRIFT_REPORT,
        edge_heartbeat_ok=True,
    )
    assert summary.healthy is True
    assert summary.source_outage_detected is False
    assert summary.stuck_drift_detected is False
    assert summary.edge_failure_detected is False


def test_exit_gate_a_controlled_source_outage_is_observable():
    down_source = SourceHealthSnapshot(name="gdacs", status="down")
    summary = build_data_health_summary(
        source_snapshots=[_HEALTHY_SOURCE, down_source],
        drift_maintenance_report=_EMPTY_DRIFT_REPORT,
        edge_heartbeat_ok=True,
    )
    assert summary.source_outage_detected is True
    assert summary.degraded_sources == ("gdacs",)
    assert summary.healthy is False


def test_exit_gate_a_stuck_drift_job_is_observable():
    summary = build_data_health_summary(
        source_snapshots=[_HEALTHY_SOURCE],
        drift_maintenance_report={"scanned": 1, "stuck": 1, "invalid": 0, "fixed": 0},
        edge_heartbeat_ok=True,
    )
    assert summary.stuck_drift_detected is True
    assert summary.stuck_drift_count == 1
    assert summary.healthy is False


def test_exit_gate_an_invalid_completed_drift_job_is_also_observable():
    summary = build_data_health_summary(
        source_snapshots=[_HEALTHY_SOURCE],
        drift_maintenance_report={"scanned": 1, "stuck": 0, "invalid": 1, "fixed": 0},
        edge_heartbeat_ok=True,
    )
    assert summary.stuck_drift_detected is True
    assert summary.invalid_drift_count == 1


def test_exit_gate_an_edge_failure_is_observable():
    summary = build_data_health_summary(
        source_snapshots=[_HEALTHY_SOURCE],
        drift_maintenance_report=_EMPTY_DRIFT_REPORT,
        edge_heartbeat_ok=False,
    )
    assert summary.edge_failure_detected is True
    assert summary.healthy is False


def test_multiple_degraded_sources_are_all_named():
    summary = build_data_health_summary(
        source_snapshots=[
            SourceHealthSnapshot(name="gdacs", status="down"),
            SourceHealthSnapshot(name="ais_ngo", status="unknown"),
            _HEALTHY_SOURCE,
        ],
        drift_maintenance_report=_EMPTY_DRIFT_REPORT,
        edge_heartbeat_ok=True,
    )
    assert set(summary.degraded_sources) == {"gdacs", "ais_ngo"}


def test_details_never_carry_raw_event_content():
    """docs/fixes.md M11: no raw sensitive Humanitarian text in metrics/
    log labels -- the summary's shape carries only counts/names, never
    event text."""
    summary = build_data_health_summary(
        source_snapshots=[_HEALTHY_SOURCE],
        drift_maintenance_report=_EMPTY_DRIFT_REPORT,
        edge_heartbeat_ok=True,
    )
    assert set(summary.details.keys()) == {"source_count", "degraded_source_count"}


# ── docs/fixes.md M14.5: live wiring ────────────────────────────────────


def test_gather_data_health_summary_returns_a_real_summary_without_manual_db_inspection():
    """The actual live caller GET /health/data uses -- gathers all three
    inputs itself from core.intel.source_registry, core.intel.
    backfill_drift_maintenance.run(), and the edge heartbeat gauge."""
    summary = gather_data_health_summary()
    assert isinstance(summary.healthy, bool)
    assert isinstance(summary.stuck_drift_count, int)
    assert isinstance(summary.degraded_sources, tuple)


def test_exit_gate_a_real_registered_source_outage_is_observable_live():
    """docs/fixes.md M14.5: a controlled source outage registered through
    the real core.intel.source_registry -- not a synthetic
    SourceHealthSnapshot -- is observable through the live caller."""
    from core.intel.source_registry import source_registry

    name = f"pytest-outage-{uuid.uuid4()}"
    source_registry.register(name, "test")
    for _ in range(5):
        source_registry.record_poll(name, error="connection refused")

    summary = gather_data_health_summary()
    assert name in summary.degraded_sources
    assert summary.source_outage_detected is True
    assert summary.healthy is False


def test_exit_gate_a_real_stuck_drift_job_is_observable_live():
    """docs/fixes.md M14.5: a genuinely stuck DriftResultDB row (M8's own
    fixture shape) is observable through the live caller, without a
    manual database query."""
    from datetime import datetime, timedelta, timezone

    from core.db.models import DriftResultDB
    from core.db.session import session_scope

    drift_id = f"pytest-stuck-{uuid.uuid4()}"
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)
    with session_scope() as db:
        db.add(DriftResultDB(
            drift_id=drift_id, event_id=f"intel:{drift_id}", domain="ocean_sar",
            lat=35.5, lon=14.1, status="computing", created_at=old, metadata_json={},
        ))

    summary = gather_data_health_summary()
    assert summary.stuck_drift_detected is True
    assert summary.stuck_drift_count >= 1
    assert summary.healthy is False


def test_exit_gate_an_edge_heartbeat_failure_is_observable_live():
    """docs/fixes.md M14.5: reading the real LIVE_EDGE_HEARTBEAT_OK gauge,
    not a synthetic edge_heartbeat_ok flag."""
    from core.observability import LIVE_EDGE_HEARTBEAT_OK, record_publisher_heartbeat

    record_publisher_heartbeat(ok=False)
    try:
        summary = gather_data_health_summary()
        assert summary.edge_failure_detected is True
        assert summary.healthy is False
    finally:
        LIVE_EDGE_HEARTBEAT_OK.set(1)
