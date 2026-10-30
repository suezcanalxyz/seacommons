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


def _cross_post(hours_ago, identifier, text):
    event = _distress((NOW - timedelta(hours=hours_ago)).isoformat())
    event.id = identifier
    event.text = text
    return event


def test_later_matched_danger_reopens_cross_post_rescue():
    from core.intel.lifecycle import distress_lifecycle, has_resolution_signal

    original = _cross_post(4, "original", "40 people in distress south of Lampedusa")
    rescue = _cross_post(3, "rescue", "40 people rescued south of Lampedusa and safe")
    danger = _cross_post(2, "danger", "40 people still in distress south of Lampedusa")
    assert not has_resolution_signal(original, [rescue, danger], now=NOW)
    assert distress_lifecycle(original, now=NOW, same_source=[rescue, danger]) == "active"


def test_cross_post_outcome_does_not_depend_on_feed_order():
    from core.intel.lifecycle import has_resolution_signal

    original = _cross_post(4, "original", "40 people in distress south of Lampedusa")
    rescue = _cross_post(3, "rescue", "40 people rescued south of Lampedusa and safe")
    danger = _cross_post(2, "danger", "40 people still in distress south of Lampedusa")
    assert not has_resolution_signal(original, [danger, rescue], now=NOW)


def test_later_matched_rescue_closes_after_earlier_danger():
    from core.intel.lifecycle import distress_lifecycle

    original = _cross_post(4, "original", "40 people in distress south of Lampedusa")
    danger = _cross_post(3, "danger", "40 people still in distress south of Lampedusa")
    rescue = _cross_post(2, "rescue", "40 people rescued south of Lampedusa and safe")
    assert distress_lifecycle(original, now=NOW, same_source=[rescue, danger]) == "resolved"


def test_ambiguous_cross_post_does_not_erase_matched_rescue():
    from core.intel.lifecycle import has_resolution_signal

    original = _cross_post(4, "original", "40 people in distress south of Lampedusa")
    rescue = _cross_post(3, "rescue", "40 people rescued south of Lampedusa and safe")
    thanks = _cross_post(2, "thanks", "40 people south of Lampedusa: thank you for the update")
    assert has_resolution_signal(original, [thanks, rescue], now=NOW)


def test_future_matched_danger_cannot_reopen_credible_cross_post_rescue():
    from core.intel.lifecycle import distress_lifecycle

    original = _cross_post(4, "original", "40 people in distress south of Lampedusa")
    rescue = _cross_post(3, "rescue", "40 people rescued south of Lampedusa and safe")
    future = _cross_post(-48, "future-danger", "40 people still in distress south of Lampedusa")
    assert distress_lifecycle(original, now=NOW, same_source=[future, rescue]) == "resolved"


def test_conflicting_group_sizes_cannot_resolve_unrelated_boat():
    """Shared geography cannot close a 40-person case using a 62-person rescue."""
    from core.intel.lifecycle import distress_lifecycle, has_resolution_signal

    original = _cross_post(4, "original-40", "40 people in distress south of Lampedusa")
    unrelated = _cross_post(2, "rescue-62", "62 people rescued south of Lampedusa and safe")
    assert not has_resolution_signal(original, [unrelated], now=NOW)
    assert distress_lifecycle(original, now=NOW, same_source=[unrelated]) == "active"


def test_matching_group_size_still_allows_same_source_resolution():
    from core.intel.lifecycle import has_resolution_signal

    original = _cross_post(4, "original-40", "40 people in distress south of Lampedusa")
    rescue = _cross_post(2, "rescue-40", "40 people rescued south of Lampedusa and safe")
    assert has_resolution_signal(original, [rescue], now=NOW)


def test_mixed_source_rescue_cannot_be_treated_as_same_source_followup():
    from core.intel.lifecycle import has_resolution_signal

    original = _cross_post(4, "original-40", "40 people in distress south of Lampedusa")
    other_ngo = _cross_post(2, "other-ngo", "40 people rescued south of Lampedusa and safe")
    other_ngo.source = "unrelated_ngo"
    assert not has_resolution_signal(original, [other_ngo], now=NOW)


def test_conflicting_french_headcount_blocks_cross_post_resolution():
    from core.intel.lifecycle import has_resolution_signal

    original = _cross_post(4, "original-40", "40 personnes en détresse au large de Lampedusa")
    unrelated = _cross_post(2, "rescue-62", "62 personnes secourues au large de Lampedusa")
    # The group-size contradiction is a safety gate independent of the
    # language-specific outcome classifier.
    assert not has_resolution_signal(original, [unrelated], now=NOW)


def test_pre_origin_rescue_reply_cannot_resolve_later_distress():
    """An older reply is not a causal follow-up to the founding report."""
    from core.intel.lifecycle import distress_lifecycle, latest_own_reply_outcome

    event = _distress(
        (NOW - timedelta(hours=2)).isoformat(),
        reposts=[{
            "posted_at": (NOW - timedelta(hours=3)).isoformat(),
            "note": "The people were rescued and are safe.",
        }],
    )
    assert latest_own_reply_outcome(event, now=NOW) is None
    assert distress_lifecycle(event, now=NOW, same_source=[]) == "active"


def test_pre_origin_danger_reply_cannot_reopen_later_resolved_report():
    from core.intel.lifecycle import distress_lifecycle, latest_own_reply_outcome

    event = _distress(
        (NOW - timedelta(hours=2)).isoformat(),
        reposts=[{
            "posted_at": (NOW - timedelta(hours=3)).isoformat(),
            "note": "They are still in distress and taking on water.",
        }],
    )
    event.text = "The people were rescued and are safe."
    assert latest_own_reply_outcome(event, now=NOW) is None
    assert distress_lifecycle(event, now=NOW, same_source=[]) == "resolved"


def test_valid_post_origin_rescue_reply_remains_decisive():
    from core.intel.lifecycle import distress_lifecycle, latest_own_reply_outcome

    event = _distress(
        (NOW - timedelta(hours=3)).isoformat(),
        reposts=[
            {
                "posted_at": (NOW - timedelta(hours=4)).isoformat(),
                "note": "They are still in distress and taking on water.",
            },
            {
                "posted_at": (NOW - timedelta(hours=1)).isoformat(),
                "note": "The people were rescued and are safe.",
            },
        ],
    )
    assert latest_own_reply_outcome(event, now=NOW) == "resolved"
    assert distress_lifecycle(event, now=NOW, same_source=[]) == "resolved"
