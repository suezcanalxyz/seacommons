# SPDX-License-Identifier: AGPL-3.0-or-later
"""Guard public SAR-responder activity against future-dated source clocks."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.live.feed import _is_fresh_sar_activity


_NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def _activity(timestamp: str, *, observation_type: str = "sar_responder_activity"):
    return SimpleNamespace(
        type="ngo_activity",
        metadata={"observation_type": observation_type},
        timestamp_utc=timestamp,
    )


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (timedelta(hours=-25), False),
        (timedelta(hours=-23), True),
        (timedelta(minutes=4), True),
        (timedelta(minutes=6), False),
        (timedelta(days=7), False),
    ],
)
def test_sar_activity_freshness_has_past_and_future_bounds(offset, expected):
    event = _activity((_NOW + offset).isoformat())
    assert _is_fresh_sar_activity(event, now=_NOW) is expected


def test_sar_activity_rejects_unparseable_observation_timestamp():
    assert not _is_fresh_sar_activity(_activity("not-a-timestamp"), now=_NOW)


def test_other_ngo_activity_is_not_filtered_by_sar_responder_ttl():
    assert _is_fresh_sar_activity(
        _activity("not-a-timestamp", observation_type="other"),
        now=_NOW,
    )
