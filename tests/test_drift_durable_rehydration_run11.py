"""Durable humanitarian drift candidates survive a cold in-memory store."""
from core.live.feed import public_drift_collection


def test_drift_reads_persisted_humanitarian_families_after_restart(monkeypatch):
    calls = []

    def persisted_events(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr("core.live.feed.intel_store.persisted_events", persisted_events)
    monkeypatch.setattr("core.live.feed.intel_store.events", lambda **kwargs: [])
    result = public_drift_collection(limit=20)
    assert result["features"] == []
    assert {tuple(call["types"]) for call in calls if "types" in call} == {
        ("distress",), ("ngo_activity",), ("iom_incident",)
    }
    assert all(call["max_age_days"] == 1 for call in calls if "types" in call)


def test_rehydrated_unlocated_distress_does_not_fabricate_drift(monkeypatch):
    """Cold-start recovery must not turn a location-free report into a point."""
    from core.intel.store import IntelEvent

    candidate = IntelEvent(
        id="cold-start-unlocated", type="distress", source="Humanitarian NGO",
        title="Distress reported without a verified position",
        text="Distress reported; coordinates not available.",
        lat=None, lon=None,
    )
    monkeypatch.setattr(
        "core.live.feed.intel_store.persisted_events",
        lambda **kwargs: [candidate] if kwargs.get("types") == ["distress"] else [],
    )
    monkeypatch.setattr("core.live.feed.intel_store.events", lambda **kwargs: [])
    result = public_drift_collection(limit=20)
    assert not any(
        feature.get("properties", {}).get("event_id") == candidate.id
        for feature in result["features"]
    )


def test_rehydrated_maritime_attack_never_generates_humanitarian_drift(monkeypatch):
    """Hard negative: persisted kinetic incident cannot become a SAR drift."""
    from datetime import datetime, timezone
    from core.intel.store import IntelEvent

    attack = IntelEvent(
        id="cold-start-attack-negative", type="distress", source="Maritime Security Bulletin",
        title="Reported vessel attack", text="Reported attack on vessel",
        lat=34.5, lon=18.0, timestamp_utc=datetime.now(timezone.utc).isoformat(),
        metadata={"maritime_domain": "security", "incident_type": "attack"},
    )
    monkeypatch.setattr(
        "core.live.feed.intel_store.persisted_events",
        lambda **kwargs: [attack] if kwargs.get("types") == ["distress"] else [],
    )
    monkeypatch.setattr("core.live.feed.intel_store.events", lambda **kwargs: [])
    result = public_drift_collection(limit=20)
    assert not any(
        feature.get("properties", {}).get("event_id") == attack.id
        for feature in result["features"]
    )
