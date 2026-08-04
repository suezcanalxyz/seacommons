# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.intel.drift_refresher import _is_drift_stale
from core.intel.store import IntelEvent


def _distress_event(event_id: str, ts: str, **meta) -> IntelEvent:
    metadata = {
        "is_distress": True,
        "drift_status": "completed",
        **meta,
    }
    return IntelEvent(
        id=event_id,
        type="twitter",
        severity="high",
        lat=35.5,
        lon=14.1,
        title="Reported distress",
        timestamp_utc=ts,
        source="Alarm Phone",
        metadata=metadata,
    )


def test_drift_is_stale_after_refresh_cadence() -> None:
    now = datetime.now(timezone.utc)
    recent = _distress_event(
        "evt-fresh",
        ts=(now - timedelta(days=1)).isoformat(),
        drift_completed_at=(now - timedelta(hours=1)).isoformat(),
    )
    stale = _distress_event(
        "evt-stale",
        ts=(now - timedelta(days=1)).isoformat(),
        drift_completed_at=(now - timedelta(hours=7)).isoformat(),
    )
    no_timestamp = _distress_event("evt-no-ts", ts=(now - timedelta(days=1)).isoformat())

    assert _is_drift_stale(recent, now=now) is False
    assert _is_drift_stale(stale, now=now) is True
    # No completion/request timestamp → not stale (leave to the manual flow).
    assert _is_drift_stale(no_timestamp, now=now) is False


def test_drift_is_stale_falls_back_to_request_time() -> None:
    now = datetime.now(timezone.utc)
    event = _distress_event(
        "evt-request",
        ts=(now - timedelta(days=2)).isoformat(),
        drift_requested_at=(now - timedelta(hours=10)).isoformat(),
    )
    assert _is_drift_stale(event, now=now) is True


def test_refresher_force_reschedules_stale_completed_drift(monkeypatch) -> None:
    from core.intel import drift_refresher

    now = datetime.now(timezone.utc)
    stale = _distress_event(
        "evt-stale-scan",
        ts=(now - timedelta(hours=30)).isoformat(),
        drift_completed_at=(now - timedelta(hours=8)).isoformat(),
        drift_status="completed",
    )
    active = _distress_event(
        "evt-active",
        ts=(now - timedelta(hours=1)).isoformat(),
        drift_completed_at=(now - timedelta(minutes=5)).isoformat(),
    )
    no_drift = _distress_event(
        "evt-no-drift",
        ts=(now - timedelta(hours=30)).isoformat(),
    )
    no_drift.metadata["drift_status"] = "failed"

    calls: list[tuple] = []
    monkeypatch.setattr(
        "core.api.routes.intel.schedule_intel_drift",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )
    store = drift_refresher.intel_store
    store._events.clear()
    store._seen.clear()
    for event in (stale, active, no_drift):
        store._events.appendleft(event)

    drift_refresher.DriftRefresher()._scan()

    # Only the stale, completed, in-window event is force-rescheduled.
    assert len(calls) == 1
    event_id, lat, lon, persons, vessel_type, observed_at = calls[0][0]
    assert event_id == "evt-stale-scan"
    assert lat == 35.5
    assert calls[0][1]["force"] is True

    store._events.clear()
    store._seen.clear()
