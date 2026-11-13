# SPDX-License-Identifier: AGPL-3.0-or-later
"""Humanitarian truth-table regression: PostgreSQL UTC-naive drift timestamps.

These tests do not access the production database or network.
"""
from datetime import datetime, timedelta, timezone

import pytest

from core.intel.humanitarian_truth_table import (
    DriftSummary,
    build_case_row,
    compute_anomaly_flags,
)


UTC_NOW = datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "created_at,now,expected_stale",
    [
        (datetime(2026, 10, 29, 6, 0), UTC_NOW, True),
        (datetime(2026, 10, 30, 7, 0), UTC_NOW, False),
        (datetime(2026, 10, 29, 6, 0, tzinfo=timezone.utc), UTC_NOW, True),
        (datetime(2026, 10, 30, 9, 0, tzinfo=timezone(timedelta(hours=2))), UTC_NOW, False),
        (datetime(2026, 10, 29, 6, 0), UTC_NOW.replace(tzinfo=None), True),
        (None, UTC_NOW, False),
    ],
)
def test_completed_drift_staleness_uses_utc_without_type_error(
    created_at, now, expected_stale,
):
    flags = compute_anomaly_flags(
        lifecycle="active",
        drifts=[DriftSummary("drift:1", "completed", created_at)],
        marker_visible=True,
        drift_visible=True,
        source_status="healthy",
        now=now,
    )
    assert ("STALE_DRIFT" in flags) is expected_stale


def test_resolved_case_with_naive_drift_does_not_raise_or_mark_stale():
    flags = compute_anomaly_flags(
        lifecycle="resolved",
        drifts=[DriftSummary("drift:1", "completed", datetime(2026, 10, 1))],
        marker_visible=False,
        drift_visible=True,
        source_status="healthy",
        now=UTC_NOW,
    )
    assert "DRIFT_AFTER_RESOLUTION" in flags
    assert "STALE_DRIFT" not in flags


def test_build_case_row_accepts_naive_postgres_created_at():
    row = build_case_row(
        event_id="case:1",
        source="alarm_phone",
        source_publication_time="2026-10-29T06:00:00Z",
        retrieved_at=None,
        last_update_at=None,
        lifecycle="active",
        drifts=[DriftSummary("drift:1", "completed", datetime(2026, 10, 29, 6))],
        marker_visible=True,
        drift_visible=True,
        publishable=True,
        source_status="healthy",
        now=UTC_NOW,
    )
    assert row.current_drift_ids == ("drift:1",)
    assert "STALE_DRIFT" in row.anomaly_flags
