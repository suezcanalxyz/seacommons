from __future__ import annotations

from datetime import datetime

from core.intel import lifecycle
from core.intel.store import IntelEvent


def _now() -> datetime:
    return datetime.fromisoformat("2026-08-06T10:00:00+00:00")


def test_alarm_phone_self_reply_resolution_leaves_live_immediately() -> None:
    event = IntelEvent(
        id="alarm-phone-52",
        type="twitter",
        severity="high",
        title="Alarm Phone",
        text="52 people in grave distress south of Lampedusa.",
        source="Alarm Phone",
        timestamp_utc="2026-08-06T08:00:00+00:00",
        metadata={
            "thread_reposts": [
                {
                    "tweet_id": "resolution-1",
                    "posted_at": "2026-08-06T09:00:00+00:00",
                    "url": "https://x.com/i/web/status/resolution-1",
                    "kind": "reply",
                    "note": "Rescued to Lampedusa! Everyone arrived safely.",
                }
            ]
        },
    )

    assert lifecycle.distress_lifecycle(event, now=_now(), same_source=[]) == "resolved"
    assert lifecycle.is_within_live_window(event, now=_now()) is False


def test_concluded_report_itself_never_enters_live() -> None:
    event = IntelEvent(
        id="alarm-phone-resolved-post",
        type="twitter",
        severity="low",
        title="Alarm Phone",
        text="The 38 people were rescued and are now safe in port.",
        source="Alarm Phone",
        timestamp_utc="2026-08-06T09:30:00+00:00",
    )

    assert lifecycle.is_within_live_window(event, now=_now()) is False


def test_unresolved_recent_report_remains_live() -> None:
    event = IntelEvent(
        id="alarm-phone-active",
        type="twitter",
        severity="high",
        title="Alarm Phone",
        text="38 people in distress without fuel. Rescue is urgently needed.",
        source="Alarm Phone",
        timestamp_utc="2026-08-06T09:30:00+00:00",
    )

    assert lifecycle.distress_lifecycle(event, now=_now(), same_source=[]) == "active"
    assert lifecycle.is_within_live_window(event, now=_now()) is True
