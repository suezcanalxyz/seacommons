from datetime import datetime, timedelta, timezone
from core.intel.drift_watchdog import _age, STUCK_AFTER, RETRY_AFTER


def test_retry_age_parses_offset_and_naive():
    now = datetime(2026, 10, 14, 10, tzinfo=timezone.utc)
    assert _age('2026-10-14T09:45:00Z', now) == timedelta(minutes=15)
    assert _age('2026-10-14T09:45:00', now) == timedelta(minutes=15)


def test_bad_timestamp_does_not_trigger_immediate_retries():
    assert _age('bogus', datetime.now(timezone.utc)) is None
    assert STUCK_AFTER > RETRY_AFTER


def test_watchdog_scans_all_durable_alarm_phone_aliases(monkeypatch):
    """The recovery scan must include aliases recognized by LIVE after deque eviction."""
    from core.intel.drift_watchdog import reconcile
    from core.intel.store import ALARM_PHONE_SOURCE_ALIASES, intel_store

    captured = {}

    def persisted_events(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(intel_store, "persisted_events", persisted_events)
    result = reconcile(launch=False, limit=17)

    assert result["candidates"] == 0
    assert result["launched"] == 0
    assert set(captured["source_in"]) == set(ALARM_PHONE_SOURCE_ALIASES)
    assert "@AlarmPhone" in captured["source_in"]
    assert "@alarmphone" in captured["source_in"]
    assert captured["max_age_days"] == 2
    assert captured["limit"] == 17


def test_watchdog_uses_verified_metadata_origin_when_canonical_columns_missing(monkeypatch):
    """Watchdog and scheduler must agree on the origin of a legacy precise fix."""
    from core.intel.drift_watchdog import reconcile
    from core.intel.store import IntelEvent, intel_store
    import core.intel.drift_service as drift_service
    import core.intel.drift_ownership as ownership
    import core.intel.lifecycle as lifecycle

    event = IntelEvent(
        id="watchdog-meta-origin", source="Alarm Phone", type="distress",
        title="Active distress", text="Boat in distress",
        lat=None, lon=None,
        metadata={
            "is_distress": True, "incident_lifecycle": "active",
            "coordinate_source": "post_text", "coordinate_review_status": "not_required",
            "lat": 34.27, "lon": 11.94,
        },
    )
    calls = []
    monkeypatch.setattr(intel_store, "persisted_events", lambda **kwargs: [event])
    monkeypatch.setattr(lifecycle, "is_within_live_window", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(drift_service, "is_auto_drift_eligible", lambda _event: (True, "eligible"))
    monkeypatch.setattr(ownership, "get_current_drift_id", lambda _id: None)
    monkeypatch.setattr(
        drift_service, "schedule_intel_drift",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )
    result = reconcile(launch=True)
    assert result["launched"] == 1
    assert calls[0][0][1:3] == (34.27, 11.94)
