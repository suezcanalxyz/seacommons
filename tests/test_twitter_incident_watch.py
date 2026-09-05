# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from core.db.models import SourceObservationDB
from core.db.session import session_scope
from core.intel.source_observation import observation_id
from core.intel.twitter_monitor import TwitterMonitor


def _clear_observations() -> None:
    with session_scope() as db:
        SourceObservationDB.__table__.create(bind=db.get_bind(), checkfirst=True)
        db.query(SourceObservationDB).delete()


def test_watch_conversation_uses_exact_bounded_query_and_records_provenance(monkeypatch):
    _clear_observations()
    monitor = TwitterMonitor(bearer_token="test-token")
    seen_queries: list[str] = []

    def fake_fetch(query: str):
        seen_queries.append(query)
        return [
            {
                "id": "watch-x-1",
                "text": "Rescued to Lampedusa, everyone is safe",
                "created_at": "2026-09-05T11:30:00Z",
                "author": "ngo",
                "url": "https://x.com/ngo/status/watch-x-1",
            },
            {
                "id": "watch-x-2",
                "text": "Further update on the same rescue",
                "created_at": "2026-09-05T11:35:00Z",
                "author": "ngo",
                "url": "https://x.com/ngo/status/watch-x-2",
            },
        ]

    monkeypatch.setattr(monitor, "_fetch", fake_fetch)
    result = monitor.watch_conversation(
        "origin-123", watch_id="watch:test", incident_id="incident:test", budget=1,
    )

    assert seen_queries == ["conversation_id:origin-123 -is:retweet"]
    assert result.source_items_seen == 1
    assert result.observations_created == 1
    assert result.observations_replayed == 0

    with session_scope() as db:
        row = db.get(SourceObservationDB, observation_id("X / Twitter", "watch-x-1"))
        assert row is not None
        assert row.provenance == {
            "collection_trigger": "incident_watch",
            "watch_id": "watch:test",
            "candidate_incident_id": "incident:test",
        }
        assert db.get(SourceObservationDB, observation_id("X / Twitter", "watch-x-2")) is None


def test_watch_conversation_replay_is_idempotent(monkeypatch):
    _clear_observations()
    monitor = TwitterMonitor(bearer_token="test-token")
    post = {
        "id": "watch-x-replay",
        "text": "Update",
        "created_at": "2026-09-05T11:30:00Z",
        "author": "ngo",
        "url": "https://x.com/ngo/status/watch-x-replay",
    }
    monkeypatch.setattr(monitor, "_fetch", lambda query: [post])

    first = monitor.watch_conversation(
        "origin-456", watch_id="watch:a", incident_id="incident:a", budget=20,
    )
    second = monitor.watch_conversation(
        "origin-456", watch_id="watch:a", incident_id="incident:a", budget=20,
    )
    assert first.observations_created == 1
    assert first.observations_replayed == 0
    assert second.observations_created == 0
    assert second.observations_replayed == 1


def test_default_watch_adapter_is_eligible_only_with_configured_x_and_explicit_tweet_id(monkeypatch):
    from core.intel import engine
    from core.intel.incident_watch import _default_adapters

    configured = TwitterMonitor(bearer_token="test-token")
    monkeypatch.setattr(engine.intel_engine, "_twitter", configured)
    adapters = _default_adapters()
    assert len(adapters) == 1
    assert adapters[0].eligible({"source_item_ids": ["123"]}) is True
    assert adapters[0].eligible({"source_item_ids": []}) is False

    monkeypatch.setattr(engine.intel_engine, "_twitter", TwitterMonitor())
    assert _default_adapters() == []
