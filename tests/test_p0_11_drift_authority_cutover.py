# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P0.11: Drift authority cutover.

Regression fixture: core.live.feed.public_drift_collection previously
selected a drift job from event.metadata["drift_job_id"] or, failing
that, the first arbitrary completed job for the event -- exactly the
anti-pattern P0.11 names ("must not rediscover arbitrary completed
jobs"). core.intel.drift_service also never called core.intel.
drift_ownership.sync_current_drift_for_incident (P0.7) at all, so the
incident's own current_drift_id pointer -- built in P0.7 -- was always
empty. Exit gate: a completed drift becomes the incident's ONE current
Drift automatically; a second completion supersedes the first; the
public feed reads only that pointer.
"""
from __future__ import annotations

import time
import uuid
from types import SimpleNamespace

import pytest

from core.intel.drift_ownership import get_current_drift_id
from core.intel.humanitarian_incident import get_incident, register, sync_incident_for_event
from core.intel.store import IntelEvent, intel_store


def _wait_for(predicate, *, tries=40, delay=0.05):
    for _ in range(tries):
        if predicate():
            return True
        time.sleep(delay)
    return False


@pytest.fixture(autouse=True)
def _fresh_tables():
    from core.db.models import DriftResultDB, HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import engine, session_scope

    HumanitarianIncidentDB.__table__.create(bind=engine(), checkfirst=True)
    IncidentTransitionDB.__table__.create(bind=engine(), checkfirst=True)
    DriftResultDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(HumanitarianIncidentDB).delete()
        db.query(IncidentTransitionDB).delete()
        db.query(DriftResultDB).delete()
    register()  # idempotent subscribe, same as bootstrap
    yield


class _FakeDriftResult:
    def __init__(self):
        self.trajectory = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": []}}
        self.cone_6h = {}
        self.cone_12h = {}
        self.cone_24h = {}
        self.impact_point = {}
        self.metadata = {"published": True}


def _run_fake_drift_completion(monkeypatch, event_id: str):
    from core.intel import drift_service

    class _FakeEngine:
        def compute(self, **_kwargs):
            return _FakeDriftResult()

    import core.drift.engine as engine_module

    monkeypatch.setattr(engine_module, "DriftEngine", _FakeEngine)
    drift_service._run_intel_drift_inner(
        event_id, 35.5, 14.1, None, "rubber_boat", "2026-09-04T08:00:00+00:00",
    )


def test_a_completed_drift_becomes_the_incidents_current_drift(monkeypatch):
    event_id = f"p011-{uuid.uuid4()}"
    event = IntelEvent(
        id=event_id, type="distress", severity="high", lat=35.5, lon=14.1,
        title=f"MAYDAY drift test [{event_id}]", text=f"MAYDAY drift test [{event_id}]", source="Alarm Phone",
        timestamp_utc="2026-09-04T08:00:00+00:00", metadata={"is_distress": True},
    )
    intel_store.add(event)
    assert _wait_for(lambda: get_incident(event_id) is not None)
    assert get_current_drift_id(event_id) is None

    _run_fake_drift_completion(monkeypatch, event_id)

    current = get_current_drift_id(event_id)
    assert current is not None


def test_a_second_completion_supersedes_the_first(monkeypatch):
    event_id = f"p011-{uuid.uuid4()}"
    event = IntelEvent(
        id=event_id, type="distress", severity="high", lat=35.5, lon=14.1,
        title=f"MAYDAY supersede test [{event_id}]", text=f"MAYDAY supersede test [{event_id}]", source="Alarm Phone",
        timestamp_utc="2026-09-04T08:00:00+00:00", metadata={"is_distress": True},
    )
    intel_store.add(event)
    assert _wait_for(lambda: get_incident(event_id) is not None)

    _run_fake_drift_completion(monkeypatch, event_id)
    first = get_current_drift_id(event_id)
    assert first is not None

    _run_fake_drift_completion(monkeypatch, event_id)
    second = get_current_drift_id(event_id)
    assert second is not None
    assert second != first  # never both -- a single pointer, always the latest


def test_a_completion_for_a_resolved_incident_never_becomes_current(monkeypatch):
    event_id = f"p011-{uuid.uuid4()}"
    event = IntelEvent(
        id=event_id, type="distress", severity="high", lat=35.5, lon=14.1,
        title=f"Rescued! All safe. [{event_id}]", text=f"Rescued! All safe. [{event_id}]",
        source="Alarm Phone",
        timestamp_utc="2026-09-04T08:00:00+00:00", metadata={"is_distress": True},
    )
    intel_store.add(event)
    assert _wait_for(lambda: get_incident(event_id) is not None and get_incident(event_id)["lifecycle"] == "resolved")

    _run_fake_drift_completion(monkeypatch, event_id)

    assert get_current_drift_id(event_id) is None


def test_public_drift_collection_reads_only_the_current_drift_id(monkeypatch):
    """The regression itself: event.metadata["drift_job_id"] must never
    be consulted, and no arbitrary completed job is ever picked."""
    from core.live.feed import public_drift_collection

    event_id = f"p011-live-{uuid.uuid4()}"
    event = IntelEvent(
        id=event_id, type="distress", severity="high", lat=35.5, lon=14.1,
        title="MAYDAY public feed test", source="alarm_phone",
        timestamp_utc="2026-09-04T08:00:00+00:00",
        metadata={
            "is_distress": True, "source_policy": "official_api",
            "coordinate_source": "media_ocr_text",
            "coordinate_review_status": "machine_ocr_unverified",
            "location_status": "positioned", "maritime_domain": "sar",
            # A stale/legacy metadata value that must NOT be consulted --
            # this drift job was never synced as current and does not exist.
            "drift_job_id": "stale-legacy-job-id",
        },
    )
    sync_incident_for_event(event, lifecycle="active")

    monkeypatch.setattr("core.live.feed.intel_store.persisted_events", lambda **_kwargs: [])
    monkeypatch.setattr("core.live.feed.intel_store.events", lambda **_kwargs: [event])

    collection = public_drift_collection(limit=50)
    event_ids = {f["properties"]["intel_event_id"] for f in collection["features"]}
    assert event_id not in event_ids  # stale metadata job_id correctly ignored

    # Now sync a REAL current_drift_id and confirm it -- and only it -- publishes.
    from core.intel.drift_ownership import sync_current_drift_for_incident

    sync_current_drift_for_incident(event_id, "real-current-job")
    fake_drift = {
        "trajectory": {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[14.0, 35.0], [14.1, 35.1]]},
            "properties": {},
        },
        "cone_24h": None, "impact_point": {}, "metadata": {"published": True},
    }
    monkeypatch.setattr("core.db.store.get_drift", lambda job_id: fake_drift if job_id == "real-current-job" else None)
    monkeypatch.setattr("core.live.feed._is_publishable_live_drift", lambda drift: True)

    collection = public_drift_collection(limit=50)
    event_ids = {f["properties"]["intel_event_id"] for f in collection["features"]}
    assert event_id in event_ids
