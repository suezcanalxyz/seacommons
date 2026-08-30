# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.intel import drift_service, ingestion_service, query_service
from core.intel.store import IntelEvent


class _EventStore:
    def __init__(self, events=None, *, add_result: bool = True):
        self._items = list(events or [])
        self.add_result = add_result
        self.added = None

    def events(self, **_kwargs):
        return list(self._items)

    def add(self, event, **_kwargs):
        self.added = event
        return self.add_result

    def get(self, event_id):
        return next((event for event in self._items if event.id == event_id), None)


class _SourceRegistry:
    def __init__(self):
        self.registered = []
        self.polls = []

    def register(self, *args):
        self.registered.append(args)

    def record_poll(self, *args, **kwargs):
        self.polls.append((args, kwargs))


def test_intel_read_model_orders_priority_then_recency(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    events = [
        IntelEvent(
            id="signal",
            type="ais_spike",
            severity="low",
            timestamp_utc=now.isoformat(),
            source="AIS",
        ),
        IntelEvent(
            id="distress",
            type="distress",
            severity="high",
            timestamp_utc=(now - timedelta(minutes=2)).isoformat(),
            source="Alarm Phone",
            metadata={"is_distress": True},
        ),
        IntelEvent(
            id="news",
            type="news",
            severity="medium",
            timestamp_utc=(now - timedelta(minutes=1)).isoformat(),
            source="RSS",
        ),
    ]
    monkeypatch.setattr(query_service, "intel_store", _EventStore(events))

    result = query_service.intel_collection(
        severity=None,
        type_filter=None,
        tier=None,
        limit=20,
        days=30,
    )

    assert [feature["properties"]["id"] for feature in result["features"]] == [
        "distress",
        "news",
        "signal",
    ]
    assert result["meta"]["operational_count"] == 1


def test_manual_ingestion_keeps_validation_outside_and_bounds_content(
    monkeypatch,
) -> None:
    store = _EventStore()
    registry = _SourceRegistry()
    monkeypatch.setattr(ingestion_service, "intel_store", store)
    monkeypatch.setattr(ingestion_service, "source_registry", registry)

    event = ingestion_service.store_manual_event(
        title="t" * 300,
        text="x" * 1200,
        source="operator",
        severity="high",
        event_type="manual",
        lat=35.5,
        lon=14.1,
        url="https://example.test/" + "u" * 600,
        linked_mmsi="123456789",
    )

    assert event is store.added
    assert len(event.title) == 255
    assert len(event.text) == 1000
    assert len(event.url) == 511
    assert event.metadata == {"injected_manually": True}
    assert registry.registered == [("Manual", "manual")]


def test_external_ingestion_is_private_by_default(monkeypatch) -> None:
    store = _EventStore()
    registry = _SourceRegistry()
    monkeypatch.setattr(ingestion_service, "intel_store", store)
    monkeypatch.setattr(ingestion_service, "source_registry", registry)

    event, added = ingestion_service.store_external_event(
        source="partner-feed",
        source_id="upstream-1",
        text="Routine maritime position report",
        title="Position report",
        url="https://example.test/report",
        lat=35.5,
        lon=14.1,
        timestamp_utc="2026-08-26T10:00:00+00:00",
        publish=False,
    )

    assert added is True
    assert event.metadata["verification_status"] == "operator_asserted"
    assert event.metadata["coordinate_source"] == "post_text"
    assert "publication_status" not in event.metadata
    assert "source_policy" not in event.metadata


def test_drift_scheduler_treats_an_existing_completed_job_as_idempotent(
    monkeypatch,
) -> None:
    event = IntelEvent(id="existing", metadata={"drift_status": "completed"})
    monkeypatch.setattr(drift_service, "intel_store", _EventStore([event]))
    monkeypatch.setattr(
        drift_service,
        "acquire_drift_slot",
        lambda: (_ for _ in ()).throw(AssertionError("slot should not be acquired")),
    )
    assert (
        drift_service.schedule_intel_drift(
            "intel:existing",
            35.5,
            14.1,
            None,
            "rubber_boat",
            "2026-08-26T10:00:00+00:00",
        )
        is True
    )


def test_drift_engine_startup_failure_is_persisted(monkeypatch) -> None:
    import core.db.store as db_store
    import core.drift.engine as drift_engine

    updates = []

    class _FailingStore:
        def get(self, _event_id):
            return None

        def update_metadata(self, event_id, *, metadata):
            updates.append((event_id, metadata))

        def broadcast_event_update(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(drift_service, "intel_store", _FailingStore())
    monkeypatch.setattr(db_store, "create_drift_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(db_store, "fail_drift_job", lambda *_args, **_kwargs: None)

    class _BrokenEngine:
        def __init__(self):
            raise PermissionError("cache unavailable")

    monkeypatch.setattr(drift_engine, "DriftEngine", _BrokenEngine)

    drift_service._run_intel_drift_inner(
        "failed-start",
        35.5,
        14.1,
        12,
        "rubber_boat",
        "2026-08-26T10:00:00+00:00",
    )

    assert updates[-1][0] == "failed-start"
    assert updates[-1][1]["drift_status"] == "failed"
    assert "cache unavailable" in updates[-1][1]["drift_error"]
