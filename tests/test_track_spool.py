# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crash replay, idempotency and capacity tests for AIS durable spool."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.db.models import VesselTrackDB, VesselTrackIngestBatchDB
from core.db.session import session_scope
from core.vessels import track_store as track_store_module
from core.vessels.track_spool import SQLiteTrackSpool, TrackSpoolFull
from core.vessels.track_store import TrackStore


def _sample(mmsi="123456789"):
    return {
        "mmsi": mmsi,
        "ts": datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc),
        "received_at": datetime(2026, 10, 15, 12, 0, 1, tzinfo=timezone.utc),
        "lat": 35.0, "lon": 14.0, "sog": 11.0,
        "cog": 90.0, "heading": 89.0, "nav_status": 0, "source": "aisstream",
    }


@pytest.fixture
def durable_store(monkeypatch, tmp_path):
    monkeypatch.setenv("SEACOMMONS_AIS_SPOOL_ENABLED", "true")
    monkeypatch.setenv("SEACOMMONS_AIS_SPOOL_ALLOW_TMP_FOR_TESTS", "true")
    monkeypatch.setenv("SEACOMMONS_AIS_SPOOL_PATH", str(tmp_path / "ais.sqlite3"))
    monkeypatch.setenv("SEACOMMONS_AIS_SPOOL_DISK_RESERVE_BYTES", "0")
    monkeypatch.setenv("SEACOMMONS_AIS_SPOOL_MAX_BYTES", "1000000")
    monkeypatch.setattr(track_store_module, "_SYNC", False)
    instance = TrackStore()
    yield instance
    instance._spool.close()


def test_enqueue_survives_reopen_and_retains_timestamp_and_provenance(tmp_path):
    path = tmp_path / "spool.sqlite3"
    first = SQLiteTrackSpool(path, reserved_disk_bytes=0, allow_temporary_test_path=True)
    first.enqueue(_sample())
    first.close()

    reopened = SQLiteTrackSpool(path, reserved_disk_bytes=0, allow_temporary_test_path=True)
    batch = reopened.claim()
    assert batch.count == 1
    assert batch.rows[0] == _sample()
    assert reopened.claim().batch_id == batch.batch_id
    assert reopened.claim().sha256 == batch.sha256
    reopened.acknowledge(batch)
    assert reopened.stats()["pending"] == 0
    reopened.close()


def test_frozen_batch_does_not_change_when_new_rows_arrive(tmp_path):
    spool = SQLiteTrackSpool(tmp_path / "spool.sqlite3", reserved_disk_bytes=0, allow_temporary_test_path=True)
    spool.enqueue(_sample("123456780"))
    frozen = spool.claim()
    spool.enqueue(_sample("123456781"))
    replay = spool.claim()
    assert replay.batch_id == frozen.batch_id
    assert replay.rows == frozen.rows
    spool.acknowledge(frozen)
    second = spool.claim()
    assert second.batch_id != frozen.batch_id
    assert second.rows[0]["mmsi"] == "123456781"
    spool.close()


def test_spool_enforces_capacity_without_accepting_lost_rows(tmp_path):
    spool = SQLiteTrackSpool(
        tmp_path / "spool.sqlite3", max_payload_bytes=64,
        reserved_disk_bytes=0, allow_temporary_test_path=True,
    )
    with pytest.raises(TrackSpoolFull):
        spool.enqueue(_sample())
    assert spool.stats()["pending"] == 0
    spool.close()


def test_disk_reserve_is_fail_closed(monkeypatch, tmp_path):
    spool = SQLiteTrackSpool(
        tmp_path / "spool.sqlite3", reserved_disk_bytes=1024,
        allow_temporary_test_path=True,
    )
    monkeypatch.setattr(
        "core.vessels.track_spool.os.statvfs",
        lambda _: SimpleNamespace(f_bavail=0, f_frsize=4096),
    )
    with pytest.raises(TrackSpoolFull, match="disk reserve"):
        spool.enqueue(_sample())
    assert spool.stats()["pending"] == 0
    spool.close()


def test_spool_refuses_relative_and_tmp_paths():
    with pytest.raises(ValueError):
        SQLiteTrackSpool("ais.sqlite3")
    with pytest.raises(ValueError):
        SQLiteTrackSpool("/tmp/ais.sqlite3")


def test_pg_batch_receipt_commits_once(durable_store):
    durable_store.on_position(
        "123456789", "SAMPLE", 35.0, 14.0,
        sog=11.0, received_at=_sample()["received_at"],
        observed_at=_sample()["ts"],
    )
    assert durable_store._spool.stats()["pending"] == 1
    assert durable_store.flush() == 1
    assert durable_store._spool.stats()["pending"] == 0
    with session_scope() as db:
        assert db.query(VesselTrackDB).filter_by(mmsi="123456789").count() == 1
        receipt = db.query(VesselTrackIngestBatchDB).one()
        assert receipt.row_count == 1
        assert len(receipt.payload_sha256) == 64


def test_ack_crash_replays_without_duplicate_postgres_inserts(durable_store, monkeypatch):
    durable_store.on_position("123456788", "SAMPLE", 35.0, 14.0)
    spool = durable_store._spool
    with monkeypatch.context() as local:
        local.setattr(
            spool, "acknowledge",
            lambda batch: (_ for _ in ()).throw(RuntimeError("simulated crash before ack")),
        )
        assert durable_store.flush() == 0
        assert spool.stats()["pending"] == 1
    with session_scope() as db:
        assert db.query(VesselTrackDB).filter_by(mmsi="123456788").count() == 1
        assert db.query(VesselTrackIngestBatchDB).count() == 1

    # Simulate process death and construction from same persistent spool path.
    spool.close()
    restarted = TrackStore()
    assert restarted.flush() == 1
    assert restarted._spool.stats()["pending"] == 0
    with session_scope() as db:
        assert db.query(VesselTrackDB).filter_by(mmsi="123456788").count() == 1
        assert db.query(VesselTrackIngestBatchDB).count() == 1
    restarted._spool.close()
    # The fixture cleanup may call close a second time; SQLite close is idempotent.


def test_db_failure_keeps_batch_for_recovery(durable_store, monkeypatch):
    from core.db import session as db_session

    durable_store.on_position("123456787", "SAMPLE", 35.0, 14.0)
    with monkeypatch.context() as local:
        def fail_session_scope():
            raise RuntimeError("postgres down")
        local.setattr(db_session, "session_scope", fail_session_scope)
        assert durable_store.flush() == 0
    assert durable_store._spool.stats()["pending"] == 1
    assert durable_store.flush() == 1
    with session_scope() as db:
        assert db.query(VesselTrackDB).filter_by(mmsi="123456787").count() == 1


def test_enqueue_failure_does_not_advance_throttle_state(durable_store, monkeypatch):
    with monkeypatch.context() as local:
        local.setattr(
            durable_store._spool, "enqueue",
            lambda row: (_ for _ in ()).throw(TrackSpoolFull("disk full")),
        )
        with pytest.raises(TrackSpoolFull):
            durable_store.on_position("123456786", "TEST", 35.0, 14.0)
    assert "123456786" not in durable_store._last_write_epoch
    assert durable_store._spool.stats()["pending"] == 0
    durable_store.on_position("123456786", "TEST", 35.0, 14.0)
    assert durable_store._spool.stats()["pending"] == 1


def test_missing_spool_path_rejects_enabled_mode(monkeypatch):
    monkeypatch.setenv("SEACOMMONS_AIS_SPOOL_ENABLED", "true")
    monkeypatch.delenv("SEACOMMONS_AIS_SPOOL_PATH", raising=False)
    with pytest.raises(RuntimeError, match="SPOOL_PATH"):
        TrackStore()
