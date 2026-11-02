# SPDX-License-Identifier: AGPL-3.0-or-later
"""Durable Alarm Phone aliases must survive bounded Live deque churn."""

from datetime import datetime, timezone

from core.intel.store import (
    ALARM_PHONE_SOURCE_ALIASES, IntelEvent, _normalised_source,
    humanitarian_source_group_key, intel_store,
)
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


def test_humanitarian_follow_up_source_key_does_not_merge_unrelated_ngos():
    assert {humanitarian_source_group_key(value) for value in ALARM_PHONE_SOURCE_ALIASES} == {
        "alarmphone"
    }
    assert humanitarian_source_group_key("Independent NGO") == "independent ngo"
    assert humanitarian_source_group_key("Alarm Phone Watch") != "alarmphone"


def test_live_follow_up_receives_same_source_replies_across_aliases(monkeypatch):
    """A newer @AlarmPhone reply belongs to an older Alarm Phone case."""
    from core.intel import humanitarian_incident

    timestamp = datetime.now(timezone.utc).isoformat()
    older = IntelEvent(
        id="alias-case-original", type="distress", source="Alarm Phone",
        timestamp_utc=timestamp, lat=35.0, lon=14.0,
        metadata={"maritime_domain": "sar", "is_distress": True},
    )
    newer = IntelEvent(
        id="alias-case-follow-up", type="distress", source="@AlarmPhone",
        timestamp_utc=timestamp, lat=35.0, lon=14.0,
        metadata={"maritime_domain": "sar", "is_distress": True},
    )
    observed: dict[str, set[str]] = {}

    def persisted_events(**kwargs):
        return [older, newer] if kwargs.get("source_in") else []

    def project(event, **kwargs):
        return {
            "type": "Feature", "id": event.id,
            "geometry": {"type": "Point", "coordinates": [14.0, 35.0]},
            "properties": {
                "id": event.id, "kind": "distress",
                "timestamp_utc": event.timestamp_utc,
            },
        }

    def resolve(event, *, now, same_source):
        observed[event.id] = {item.id for item in same_source}
        return {
            "lifecycle": "active", "incident_status": "active",
            "reported_at": timestamp, "last_update_at": timestamp,
            "state_changed_at": timestamp, "resolved_at": None,
        }

    monkeypatch.setattr(intel_store, "persisted_events", persisted_events)
    monkeypatch.setattr(intel_store, "events", lambda **kwargs: [])
    monkeypatch.setattr(intel_store, "live_retained_events", lambda **kwargs: [])
    monkeypatch.setattr(feed, "_public_intel_feature", project)
    monkeypatch.setattr(feed, "is_useful_public_case_feature", lambda feature: True)
    monkeypatch.setattr(feed.lifecycle, "is_within_live_retention_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(feed, "dedupe_public_case_items", lambda features: features)
    monkeypatch.setattr(feed, "_published_open_episode_features", lambda limit: [])
    monkeypatch.setattr(feed, "_published_security_hypothesis_features", lambda limit: [])
    monkeypatch.setattr(feed, "_attach_cross_modal_evidence", lambda features, *, now: None)
    monkeypatch.setattr(humanitarian_incident, "resolve_public_incident_state", resolve)

    feed.public_signal_collection(mode="humanitarian", limit=10)

    assert observed["alias-case-original"] == {"alias-case-original", "alias-case-follow-up"}
    assert observed["alias-case-follow-up"] == observed["alias-case-original"]
