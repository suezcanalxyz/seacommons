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
    assert "@alarm_phone" in requests[1]["source_in"]
    assert "alarmphone" in requests[1]["source_in"]
