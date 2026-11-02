# SPDX-License-Identifier: AGPL-3.0-or-later
"""Durable Alarm Phone aliases must survive bounded Live deque churn."""

from core.intel.store import ALARM_PHONE_SOURCE_ALIASES, _normalised_source, intel_store
from core.live import feed


def test_durable_alarm_phone_source_aliases_are_one_identity():
    assert {"Alarm Phone", "alarm_phone", "alarmphone", "@alarm_phone", "@AlarmPhone"} <= set(
        ALARM_PHONE_SOURCE_ALIASES
    )
    assert {_normalised_source(value) for value in ALARM_PHONE_SOURCE_ALIASES} == {
        "alarmphone"
    }


def test_live_signals_and_drifts_read_all_durable_alarm_phone_aliases(monkeypatch):
    """Exact-match SQL source_in must include every known collector spelling."""
    seen: list[tuple[str, ...]] = []

    def persisted_events(**kwargs):
        if kwargs.get("source_in"):
            seen.append(tuple(kwargs["source_in"]))
        return []

    monkeypatch.setattr(intel_store, "persisted_events", persisted_events)
    monkeypatch.setattr(intel_store, "events", lambda **kwargs: [])
    monkeypatch.setattr(intel_store, "live_retained_events", lambda **kwargs: [])
    monkeypatch.setattr(feed, "_published_open_episode_features", lambda limit: [])
    monkeypatch.setattr(feed, "_published_security_hypothesis_features", lambda limit: [])
    monkeypatch.setattr(feed, "_attach_cross_modal_evidence", lambda features, *, now: None)

    signals = feed.public_signal_collection(mode="humanitarian", limit=10)
    drifts = feed.public_drift_collection(limit=10)

    assert signals["features"] == []
    assert drifts["features"] == []
    assert len(seen) == 2
    assert all(set(aliases) == set(ALARM_PHONE_SOURCE_ALIASES) for aliases in seen)
