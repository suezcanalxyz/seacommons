# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prevent future-dated humanitarian updates from extending the Live window."""

from datetime import datetime, timedelta, timezone

from core.intel.lifecycle import is_within_live_retention_window
from core.intel.store import IntelEvent


NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def _distress(timestamp, *, reposts=None):
    return IntelEvent(
        id="clock-skew-humanitarian", type="distress", severity="high",
        title="Reported distress", text="Reported distress",
        source="alarm_phone", timestamp_utc=timestamp,
        metadata={"thread_reposts": reposts or []},
    )


def test_far_future_repost_cannot_reactivate_expired_case():
    event = _distress(
        (NOW - timedelta(hours=26)).isoformat(),
        reposts=[{"posted_at": (NOW + timedelta(days=10)).isoformat()}],
    )
    assert not is_within_live_retention_window(event, now=NOW)


def test_far_future_repost_does_not_hide_fresh_real_report():
    event = _distress(
        (NOW - timedelta(hours=2)).isoformat(),
        reposts=[{"posted_at": (NOW + timedelta(days=10)).isoformat()}],
    )
    assert is_within_live_retention_window(event, now=NOW)


def test_only_future_dated_report_cannot_be_live():
    event = _distress((NOW + timedelta(days=10)).isoformat())
    assert not is_within_live_retention_window(event, now=NOW)


def test_five_minute_source_clock_skew_is_tolerated():
    event = _distress((NOW + timedelta(minutes=4)).isoformat())
    assert is_within_live_retention_window(event, now=NOW)


def test_valid_recent_repost_can_extend_older_case_window():
    event = _distress(
        (NOW - timedelta(hours=26)).isoformat(),
        reposts=[{"posted_at": (NOW - timedelta(hours=1)).isoformat()}],
    )
    assert is_within_live_retention_window(event, now=NOW)
