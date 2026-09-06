from __future__ import annotations

import importlib

import pytest


def _store():
    try:
        return importlib.import_module("core.intel.episode_store")
    except ModuleNotFoundError:
        pytest.fail("core.intel.episode_store is required")


def _feature() -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [14.1, 35.5]},
        "properties": {
            "episode_id": "episode:subj:mmsi:211879870:gap_episode:1",
            "episode_family": "gap_episode",
            "subject_ids": ["subj:mmsi:211879870"],
            "first_observed_at": "2026-09-06T08:00:00+00:00",
            "last_observed_at": "2026-09-06T09:00:00+00:00",
            "related_signal_ids": ["gap:a", "gap:b"],
            "independence_groups": ["ais_sensor_lineage"],
            "verification_status": "single_source_multi_indicator",
        },
    }


def test_episode_fingerprint_is_deterministic_and_order_stable() -> None:
    store = _store()
    kwargs = dict(
        subject_ids=("subj:mmsi:211879870",),
        family="gap_episode",
        signal_ids=("gap:a", "gap:b"),
        first_observed_at="2026-09-06T08:00:00+00:00",
        last_observed_at="2026-09-06T09:00:00+00:00",
        method_version="maritime-episode-v1",
    )
    first = store.episode_fingerprint(**kwargs)
    kwargs["signal_ids"] = ("gap:b", "gap:a")
    second = store.episode_fingerprint(**kwargs)
    assert first == second
    assert len(first) == 64


def test_save_episode_is_idempotent_on_replay() -> None:
    store = _store()
    from core.db.models import MaritimeEpisodeDB
    from core.db.session import engine, session_scope

    MaritimeEpisodeDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(MaritimeEpisodeDB).delete()
    first = store.save_episode(_feature())
    second = store.save_episode(_feature())
    assert first.episode_id == second.episode_id
    with session_scope() as db:
        rows = db.query(MaritimeEpisodeDB).all()
        assert len(rows) == 1
        assert rows[0].verification_status == "single_source_multi_indicator"
