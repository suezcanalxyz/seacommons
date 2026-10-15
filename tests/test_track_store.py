# SPDX-License-Identifier: AGPL-3.0-or-later
"""AIS track history store."""
from __future__ import annotations

import os

os.environ["SEACOMMONS_TRACK_STORE_SYNC"] = "1"

import time
from datetime import datetime, timedelta, timezone

import pytest

from core.vessels.track_store import TrackStore


@pytest.fixture
def store():
    s = TrackStore()
    yield s


def _pos(store, mmsi, lat, lon, sog=10.0, nav=0, recv=None):
    store.on_position(mmsi, "TEST", lat, lon, sog=sog, cog=90.0, heading=88.0,
                      nav_status=nav, received_at=recv or datetime.now(timezone.utc))


def test_position_is_stored(store):
    _pos(store, "111000111", 35.0, 18.0)
    rows = store.track("111000111")
    assert len(rows) == 1
    assert rows[0]["lat"] == 35.0 and rows[0]["sog"] == 10.0


def test_throttled_within_interval(store):
    _pos(store, "111000222", 35.0, 18.0)
    _pos(store, "111000222", 35.0001, 18.0001)   # < 60 s later, tiny move
    assert len(store.track("111000222")) == 1


def test_nav_status_change_breaks_throttle(store):
    _pos(store, "111000333", 35.0, 18.0, nav=0)
    _pos(store, "111000333", 35.0001, 18.0001, nav=1)   # status change → kept
    assert len(store.track("111000333")) == 2


def test_long_jump_breaks_throttle(store):
    _pos(store, "111000444", 35.0, 18.0)
    _pos(store, "111000444", 35.2, 18.3)   # ~15 nm jump → kept
    assert len(store.track("111000444")) == 2


def test_silent_since(store):
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    _pos(store, "111000555", 35.0, 18.0, sog=12.0, recv=old)
    # force the in-memory last-seen clock back
    store._last["111000555"].ts = time.time() - 7200
    quiet = dict(store.silent_since(min_silent_s=3600))
    assert "111000555" in quiet
    assert dict(store.silent_since(min_silent_s=3 * 3600)) == {}


def test_recent_last_seen_hydrates_gap_state_after_restart(store):
    mmsi = "111000556"
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    _pos(store, mmsi, 35.2, 18.2, sog=11.0, recv=old)

    restarted = TrackStore()
    assert restarted._last == {}
    assert restarted.hydrate_recent_last_seen(max_age_hours=12) >= 1

    quiet = dict(restarted.silent_since(min_silent_s=3600))
    assert mmsi in quiet
    assert quiet[mmsi].lat == 35.2
    assert quiet[mmsi].sog == 11.0


def test_positions_between_bbox(store):
    now = datetime.now(timezone.utc)
    _pos(store, "111000666", 35.0, 18.0, recv=now)
    _pos(store, "111000777", 10.0, 5.0, recv=now)
    hits = store.positions_between(now - timedelta(minutes=5), now + timedelta(minutes=5),
                                   bbox=(17.0, 34.0, 19.0, 36.0))
    assert {h["mmsi"] for h in hits} == {"111000666"}


def test_recent_tracks_batches_and_limits_each_mmsi(store):
    now = datetime.now(timezone.utc)
    for index in range(4):
        _pos(store, "111001111", 35.0 + index / 100, 18.0, nav=index % 2, recv=now + timedelta(minutes=index))
        _pos(store, "222002222", 36.0 + index / 100, 19.0, nav=index % 2, recv=now + timedelta(minutes=index))

    tracks = store.recent_tracks(
        {"111001111", "222002222"},
        since=now - timedelta(minutes=1),
        limit_per_mmsi=2,
    )

    assert set(tracks) == {"111001111", "222002222"}
    assert all(len(points) == 2 for points in tracks.values())
    assert tracks["111001111"][-1]["lat"] == 35.03


def test_prune(store, monkeypatch):
    from core import object_store
    monkeypatch.setenv("AIS_PRUNE_APPROVED", "true")
    monkeypatch.setenv("AIS_RETENTION_POLICY_ID", "test-policy-2026")
    from core.config import config
    monkeypatch.setattr(config, 'OBJECT_STORAGE_ENDPOINT', 'test.local')
    monkeypatch.setattr(config, 'OBJECT_STORAGE_ACCESS_KEY', 'test-key')
    monkeypatch.setattr(config, 'OBJECT_STORAGE_SECRET_KEY', 'test-secret')
    payloads = {}
    monkeypatch.setattr(object_store, 'put', lambda key, data, mime: payloads.__setitem__(key, data))
    monkeypatch.setattr(object_store, 'get', lambda key: payloads[key])
    old = datetime.now(timezone.utc) - timedelta(days=90)
    _pos(store, "111000888", 35.0, 18.0, recv=old)
    assert store.prune(older_than_days=60) == 1
    assert store.track("111000888") == []


def test_old_ais_is_deleted_only_after_verified_cold_archival(monkeypatch):
    import gzip
    import json
    monkeypatch.setenv("AIS_PRUNE_APPROVED", "true")
    monkeypatch.setenv("AIS_RETENTION_POLICY_ID", "test-policy-2026")
    from core.config import config
    from core import object_store
    from core.db.models import VesselTrackDB
    from core.db.session import session_scope

    monkeypatch.setattr(config, 'OBJECT_STORAGE_ENDPOINT', 'test.local')
    monkeypatch.setattr(config, 'OBJECT_STORAGE_ACCESS_KEY', 'test-key')
    monkeypatch.setattr(config, 'OBJECT_STORAGE_SECRET_KEY', 'test-secret')
    archive = {}
    monkeypatch.setattr(object_store, 'put', lambda key, data, content_type: archive.__setitem__(key, data))
    monkeypatch.setattr(object_store, 'get', lambda key: archive[key])

    old = datetime.now(timezone.utc) - timedelta(days=90)
    with session_scope() as db:
        db.add(VesselTrackDB(mmsi='111765432', ts=old, received_at=old,
                             lat=35.1, lon=14.1, source='aisstream'))
    store = TrackStore()
    count = store.prune(older_than_days=60)
    assert count >= 1
    assert archive
    retained = [r for raw in archive.values()
                for r in json.loads(gzip.decompress(raw))['rows'] if r['mmsi'] == '111765432']
    assert len(retained) == 1
    with session_scope() as db:
        assert db.query(VesselTrackDB).filter(VesselTrackDB.mmsi == '111765432').count() == 0


def test_cold_archive_failure_preserves_original_rows(monkeypatch):
    monkeypatch.setenv("AIS_PRUNE_APPROVED", "true")
    monkeypatch.setenv("AIS_RETENTION_POLICY_ID", "test-policy-2026")
    from core.config import config
    from core import object_store
    from core.db.models import VesselTrackDB
    from core.db.session import session_scope

    monkeypatch.setattr(config, 'OBJECT_STORAGE_ENDPOINT', 'test.local')
    monkeypatch.setattr(config, 'OBJECT_STORAGE_ACCESS_KEY', 'test-key')
    monkeypatch.setattr(config, 'OBJECT_STORAGE_SECRET_KEY', 'test-secret')
    def fail(*_args):
        raise RuntimeError('storage unavailable')
    monkeypatch.setattr(object_store, 'put', fail)
    old = datetime.now(timezone.utc) - timedelta(days=90)
    with session_scope() as db:
        db.add(VesselTrackDB(mmsi='111765433', ts=old, received_at=old,
                             lat=35.2, lon=14.2, source='aisstream'))
    assert TrackStore().prune(older_than_days=60) == 0
    with session_scope() as db:
        assert db.query(VesselTrackDB).filter(VesselTrackDB.mmsi == '111765433').count() == 1
        db.query(VesselTrackDB).filter(VesselTrackDB.mmsi == '111765433').delete()


def test_prune_requires_explicit_policy_id(monkeypatch):
    """Neither a default nor an enable flag alone authorizes deletion."""
    from core import object_store

    monkeypatch.delenv("AIS_PRUNE_APPROVED", raising=False)
    monkeypatch.delenv("AIS_RETENTION_POLICY_ID", raising=False)
    monkeypatch.setattr(object_store, "put", lambda *_: pytest.fail("unapproved archive PUT"))
    assert TrackStore().prune(older_than_days=1) == 0

    monkeypatch.setenv("AIS_PRUNE_APPROVED", "true")
    assert TrackStore().prune(older_than_days=1) == 0

    monkeypatch.delenv("AIS_PRUNE_APPROVED")
    monkeypatch.setenv("AIS_RETENTION_POLICY_ID", "test-policy-2026")
    assert TrackStore().prune(older_than_days=1) == 0


def test_failed_flush_requeues_in_order_and_recovers(monkeypatch):
    """A transient DB failure must not discard in-memory observations."""
    from contextlib import contextmanager
    from core.db import session as db_session

    attempts = []
    persisted = []

    class FakeSession:
        def bulk_insert_mappings(self, model, rows):
            attempts.append([r["mmsi"] for r in rows])
            if len(attempts) == 1:
                raise RuntimeError("transient database outage")
            persisted.extend(r["mmsi"] for r in rows)

    @contextmanager
    def fake_session_scope():
        yield FakeSession()

    monkeypatch.setattr(db_session, "session_scope", fake_session_scope)
    store = TrackStore()
    store._buffer = [
        {"mmsi": "111000001"},
        {"mmsi": "111000002"},
    ]
    assert store.flush() == 0
    assert [r["mmsi"] for r in store._buffer] == ["111000001", "111000002"]
    store._buffer.append({"mmsi": "111000003"})
    assert store.flush() == 3
    assert store._buffer == []
    assert attempts == [
        ["111000001", "111000002"],
        ["111000001", "111000002", "111000003"],
    ]
    assert persisted == ["111000001", "111000002", "111000003"]
