from __future__ import annotations

import logging
import uuid

from core.api.main import _run_intel_sync_tick
from core.intel.source_registry import source_registry
from core.observability import (
    record_drift_maintenance_report,
    record_hypothesis_transition,
    refresh_source_health_gauges,
)
from prometheus_client import generate_latest


def test_split_runtime_sync_metrics_record_success_and_failure(caplog) -> None:
    def failed_sync() -> tuple[int, int]:
        raise RuntimeError("database unavailable with private detail")

    with caplog.at_level(logging.WARNING, logger="seacommons.api"):
        failures = _run_intel_sync_tick(failed_sync, consecutive_failures=0)
    assert failures == 1
    assert "error_type=RuntimeError" in caplog.text
    assert "private detail" not in caplog.text

    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="seacommons.api"):
        failures = _run_intel_sync_tick(failed_sync, consecutive_failures=2)
    assert failures == 3
    assert any(record.levelno == logging.ERROR for record in caplog.records)

    with caplog.at_level(logging.INFO, logger="seacommons.api"):
        failures = _run_intel_sync_tick(lambda: (2, 3), consecutive_failures=failures)
    assert failures == 0
    assert "recovered after 3 consecutive failure(s)" in caplog.text

    metrics = generate_latest().decode()
    assert 'seacommons_intel_sync_runs_total{outcome="failure"}' in metrics
    assert 'seacommons_intel_sync_runs_total{outcome="success"}' in metrics
    assert "seacommons_intel_sync_consecutive_failures 0.0" in metrics
    assert "seacommons_intel_sync_last_success_unixtime" in metrics


def test_intel_source_health_metrics_are_aggregated_without_source_labels() -> None:
    name = f"pytest-source-{uuid.uuid4()}"
    source_registry.register(name, "test")
    source_registry.record_poll(name, events_found=2)

    refresh_source_health_gauges()
    metrics = generate_latest().decode()

    assert 'seacommons_intel_sources{status="active"}' in metrics
    assert "seacommons_intel_source_events_last_hour" in metrics
    assert name not in metrics


# ── docs/fixes.md M11 ────────────────────────────────────────────────────

def test_record_hypothesis_transition_increments_the_labelled_counter() -> None:
    record_hypothesis_transition("dark_transit", "review_ready")
    metrics = generate_latest().decode()
    assert (
        'seacommons_hypothesis_events_total{hypothesis_type="dark_transit",state="review_ready"}'
        in metrics
    )


def test_record_hypothesis_transition_never_raises_on_a_broken_backend(monkeypatch) -> None:
    import core.observability as observability_module

    def _boom(*args, **kwargs):
        raise RuntimeError("metrics backend down")

    monkeypatch.setattr(observability_module.HYPOTHESIS_EVENTS, "labels", _boom)
    record_hypothesis_transition("dark_transit", "assessed")  # must not raise


def test_record_drift_maintenance_report_sets_stuck_and_invalid_gauges() -> None:
    record_drift_maintenance_report({"scanned": 5, "stuck": 3, "invalid": 2, "fixed": 0})
    metrics = generate_latest().decode()
    assert 'seacommons_drift_status{status="stuck"} 3.0' in metrics
    assert 'seacommons_drift_status{status="invalid"} 2.0' in metrics


def test_record_drift_maintenance_report_never_raises_on_missing_keys() -> None:
    record_drift_maintenance_report({})  # must not raise, defaults to 0
