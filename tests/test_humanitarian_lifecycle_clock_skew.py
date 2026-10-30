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


def test_future_resolution_reply_cannot_close_a_fresh_case():
    from core.intel.lifecycle import distress_lifecycle, is_within_live_window

    event = _distress(
        (NOW - timedelta(hours=2)).isoformat(),
        reposts=[{"posted_at": (NOW + timedelta(days=2)).isoformat(),
                  "note": "The people were rescued and are safe."}],
    )
    assert distress_lifecycle(event, now=NOW, same_source=[]) == "active"
    assert is_within_live_window(event, now=NOW)


def test_future_danger_reply_cannot_reopen_a_resolved_case():
    from core.intel.lifecycle import distress_lifecycle

    event = _distress(
        (NOW - timedelta(hours=2)).isoformat(),
        reposts=[
            {"posted_at": (NOW - timedelta(hours=1)).isoformat(),
             "note": "The people were rescued and are safe."},
            {"posted_at": (NOW + timedelta(days=2)).isoformat(),
             "note": "They are still in distress and taking on water."},
        ],
    )
    assert distress_lifecycle(event, now=NOW, same_source=[]) == "resolved"


def test_malformed_repost_cannot_override_valid_resolution():
    from core.intel.lifecycle import distress_lifecycle

    event = _distress(
        (NOW - timedelta(hours=2)).isoformat(),
        reposts=[
            {"posted_at": (NOW - timedelta(hours=1)).isoformat(),
             "note": "The people were rescued and are safe."},
            {"posted_at": "not-a-timestamp",
             "note": "Still in distress."},
            "bad-provider-entry",
        ],
    )
    assert distress_lifecycle(event, now=NOW, same_source=[]) == "resolved"


def test_ambiguous_reply_cannot_undo_confirmed_rescue():
    from core.intel.lifecycle import distress_lifecycle, latest_own_reply_outcome

    event = _distress(
        (NOW - timedelta(hours=3)).isoformat(),
        reposts=[
            {"posted_at": (NOW - timedelta(hours=2)).isoformat(),
             "note": "The people were rescued and are safe."},
            {"posted_at": (NOW - timedelta(hours=1)).isoformat(),
             "note": "Thank you to all the volunteers."},
        ],
    )
    assert latest_own_reply_outcome(event, now=NOW) == "resolved"
    assert distress_lifecycle(event, now=NOW, same_source=[]) == "resolved"


def test_later_decisive_danger_still_reopens_after_ambiguous_reply():
    from core.intel.lifecycle import distress_lifecycle

    event = _distress(
        (NOW - timedelta(hours=4)).isoformat(),
        reposts=[
            {"posted_at": (NOW - timedelta(hours=3)).isoformat(),
             "note": "The people were rescued and are safe."},
            {"posted_at": (NOW - timedelta(hours=2)).isoformat(),
             "note": "Thank you to all the volunteers."},
            {"posted_at": (NOW - timedelta(hours=1)).isoformat(),
             "note": "They are still in distress and taking on water."},
        ],
    )
    assert distress_lifecycle(event, now=NOW, same_source=[]) == "active"


def test_only_ambiguous_reply_still_requires_review():
    from core.intel.lifecycle import latest_own_reply_outcome

    event = _distress(
        (NOW - timedelta(hours=2)).isoformat(),
        reposts=[{"posted_at": (NOW - timedelta(hours=1)).isoformat(),
                  "note": "Thank you to all the volunteers."}],
    )
    assert latest_own_reply_outcome(event, now=NOW) == "needs_review"


def test_future_same_source_resolution_cannot_close_current_distress():
    from core.intel.lifecycle import distress_lifecycle

    event = _distress((NOW - timedelta(hours=2)).isoformat())
    event.text = "40 people in distress south of Lampedusa"
    future = _distress((NOW + timedelta(days=2)).isoformat())
    future.id = "future-resolution"
    future.text = "40 people rescued south of Lampedusa and safe"
    assert distress_lifecycle(event, now=NOW, same_source=[future]) == "active"


def test_credible_same_source_resolution_still_closes_case():
    from core.intel.lifecycle import distress_lifecycle

    event = _distress((NOW - timedelta(hours=2)).isoformat())
    event.text = "40 people in distress south of Lampedusa"
    followup = _distress((NOW - timedelta(hours=1)).isoformat())
    followup.id = "valid-resolution"
    followup.text = "40 people rescued south of Lampedusa and safe"
    assert distress_lifecycle(event, now=NOW, same_source=[followup]) == "resolved"
