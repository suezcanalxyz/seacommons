# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prevent serialized boolean flags from promoting context to SAR operations."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.intel.store import IntelEvent


@pytest.mark.parametrize("flag", [False, "false", "FALSE", " no ", "0", 0, None, "unknown", 2])
def test_non_distress_flags_remain_context(flag):
    event = IntelEvent(
        id="non-distress",
        type="twitter",
        severity="high",
        source="Alarm Phone",
        timestamp_utc="2026-11-02T00:00:00+00:00",
        metadata={"is_distress": flag},
    )
    assert event.tier() == "news"
    assert event.canonical_columns()["operational_tier"] == "news"
    assert event.priority() >= 10


@pytest.mark.parametrize("flag", [True, "true", "TRUE", " yes ", "1", 1])
def test_explicit_distress_flags_remain_operational(flag):
    event = IntelEvent(
        id="confirmed-distress",
        type="twitter",
        severity="high",
        timestamp_utc="2026-11-02T00:00:00+00:00",
        metadata={"is_distress": flag},
    )
    assert event.tier() == "operational"
    assert event.canonical_columns()["operational_tier"] == "operational"


def test_explicit_distress_event_type_remains_operational():
    event = IntelEvent(
        id="distress-type",
        type="distress",
        timestamp_utc="2026-11-02T00:00:00+00:00",
        metadata={},
    )
    assert event.tier() == "operational"


def test_durable_refresher_recovers_alternate_alarm_phone_source(monkeypatch):
    from core.intel import drift_refresher

    event = IntelEvent(
        id="evicted-alias",
        type="twitter",
        severity="high",
        source="@alarm_phone",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        metadata={"is_distress": True, "drift_status": "completed"},
    )
    requests = []
    monkeypatch.setattr(drift_refresher.intel_store, "events", lambda **kwargs: [])
    def persisted_events(**kwargs):
        requests.append(kwargs)
        return [event] if kwargs.get("source_in") and event.source in kwargs["source_in"] else []
    monkeypatch.setattr(drift_refresher.intel_store, "persisted_events", persisted_events)

    candidates = drift_refresher._refresh_candidates()
    assert [candidate.id for candidate in candidates] == ["evicted-alias"]
    source_queries = [request["source_in"] for request in requests if "source_in" in request]
    assert len(source_queries) == 1
    assert "@alarm_phone" in source_queries[0]
    assert "alarmphone" in source_queries[0]

def test_serialized_false_alarm_phone_report_does_not_enter_public_live():
    from core.live.projection import _public_intel_feature

    event = IntelEvent(
        id="non-distress-public",
        type="twitter",
        severity="high",
        source="Alarm Phone",
        title="Historical update, no active distress",
        text="A contextual public report, not an ongoing rescue request.",
        lat=35.5,
        lon=14.1,
        timestamp_utc="2026-11-02T00:00:00+00:00",
        metadata={
            "is_distress": "false",
            "tweet_id": "public-context-123",
            "publication_status": "published",
            "source_policy": "official_api",
            "maritime_domain": "sar",
        },
    )
    assert _public_intel_feature(event) is None
