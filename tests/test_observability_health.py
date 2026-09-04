# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M11: analyst data-health summary.

Exit gate, verbatim: "controlled source outage, stuck Drift job and
edge failure are all observable without inspecting the database
manually."
"""
from __future__ import annotations

from core.observability_health import SourceHealthSnapshot, build_data_health_summary

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
