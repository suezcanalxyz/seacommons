# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recovery of durable drift records with missing request timestamps."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from core.intel import drift_watchdog as watchdog


@pytest.mark.parametrize(
    ("status", "elapsed", "expected"),
    [
        ("computing", None, None),
        ("failed", None, None),
        ("computing", timedelta(minutes=15), "precise_running"),
        ("computing", timedelta(minutes=90), "precise_running"),
        ("computing", timedelta(hours=2), None),
        ("failed", timedelta(minutes=15), "precise_pending"),
        ("failed", timedelta(minutes=30), None),
        ("completed", None, None),
    ],
)
def test_retry_deferral_requires_a_real_recent_timestamp(status, elapsed, expected):
    assert watchdog._defer_retry(status, elapsed) == expected


@pytest.mark.parametrize("stale_status", ["computing", "failed"])
def test_watchdog_recovers_missing_timestamp_without_running_model(monkeypatch, stale_status):
    """A restart-era status without a request time must not be stuck forever."""
    from core.intel import drift_service, drift_ownership, lifecycle, store

    event = SimpleNamespace(
        id="alarm-recovered",
        source="@AlarmPhone",
        timestamp_utc="2026-11-02T20:00:00+00:00",
        metadata={
            "is_distress": True,
            "incident_lifecycle": "active",
            "drift_status": stale_status,
            "coordinate_source": "post_text",
        },
    )
    launches = []

    monkeypatch.setattr(store.intel_store, "persisted_events", lambda **kwargs: [event])
    monkeypatch.setattr(watchdog, "source_is_alarm_phone", lambda e: True)
    monkeypatch.setattr(watchdog, "explicit_distress_flag", lambda flag: True)
    monkeypatch.setattr(lifecycle, "is_within_live_window", lambda e, now: True)
    monkeypatch.setattr(drift_service, "is_auto_drift_eligible", lambda e: (True, "eligible"))
    monkeypatch.setattr(drift_service, "drift_origin_coordinates", lambda e: (34.27, 11.94))
    monkeypatch.setattr(drift_ownership, "get_current_drift_id", lambda event_id: None)
    monkeypatch.setattr(
        drift_service, "schedule_intel_drift",
        lambda *args, **kwargs: launches.append((args, kwargs)) or True,
    )

    report = watchdog.reconcile(launch=True)
    assert report["candidates"] == 1
    assert report["precise_eligible"] == 1
    assert report["precise_pending"] == 1
    assert report["precise_running"] == 0
    assert report["launched"] == 1
    assert len(launches) == 1
    assert launches[0][0][1:3] == (34.27, 11.94)
    assert launches[0][1]["force"] is True
