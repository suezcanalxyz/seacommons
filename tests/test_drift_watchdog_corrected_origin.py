# SPDX-License-Identifier: AGPL-3.0-or-later
"""A corrected distress location invalidates an older completed drift origin."""
from types import SimpleNamespace

import pytest

from core.intel import drift_watchdog as watchdog


def _completed(lat=34.27, lon=11.94):
    return {
        "status": "completed",
        "lat": lat,
        "lon": lon,
        "trajectory": {"type": "LineString", "coordinates": [[lon, lat]]},
        "cone_24h": {"type": "Polygon", "coordinates": []},
    }


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (_completed(), True),
        (_completed(lat=34.15), False),
        (_completed(lon=12.11), False),
        (_completed(lat="nan"), False),
        (_completed(lat=None), False),
        ({"status": "completed", "trajectory": [1], "cone_24h": [1]}, False),
        ({**_completed(), "status": "failed"}, False),
        ({**_completed(), "cone_24h": None}, False),
        (None, False),
    ],
)
def test_completed_drift_requires_matching_finite_origin(result, expected):
    assert watchdog._completed_drift_matches_origin(result, 34.27, 11.94) is expected


@pytest.mark.parametrize("stale", [False, True])
def test_watchdog_recomputes_only_when_completed_origin_is_stale(monkeypatch, stale):
    """Exercise the durable follow-up path without starting OpenDrift."""
    from core.intel import drift_service, drift_ownership, lifecycle, store
    from core.db import store as db_store

    event = SimpleNamespace(
        id="alarm-corrected-position",
        source="@AlarmPhone",
        timestamp_utc="2026-11-02T20:00:00+00:00",
        metadata={
            "is_distress": True,
            "incident_lifecycle": "active",
            "drift_status": "completed",
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
    monkeypatch.setattr(drift_ownership, "get_current_drift_id", lambda event_id: "old-drift")
    monkeypatch.setattr(
        db_store, "get_drift",
        lambda job_id: _completed(lat=34.15 if stale else 34.27),
    )
    monkeypatch.setattr(
        drift_service, "schedule_intel_drift",
        lambda *args, **kwargs: launches.append((args, kwargs)) or True,
    )

    report = watchdog.reconcile(launch=True)
    assert report["precise_eligible"] == 1
    assert report["precise_completed"] == (0 if stale else 1)
    assert report["launched"] == (1 if stale else 0)
    assert len(launches) == (1 if stale else 0)
    if stale:
        assert launches[0][0][1:3] == (34.27, 11.94)
        assert launches[0][1]["force"] is True
