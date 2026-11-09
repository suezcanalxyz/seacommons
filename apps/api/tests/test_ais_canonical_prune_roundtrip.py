# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exercise the *actual* TrackStore.prune serializer against disposable SQL.

SQLite deliberately cannot validate PostgreSQL row locks; a separate PostgreSQL
two-session and S3-compatible restore drill is still required before retention.
"""
import gzip
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


@pytest.mark.parametrize("corrupt", [False, True])
def test_canonical_prune_archive_roundtrip_and_fail_closed(monkeypatch, corrupt):
    from core.vessels import track_store
    from core.db import models, session as db_session
    from core import object_store

    base = declarative_base()

    class DisposableTrack(base):
        __tablename__ = "disposable_ais_archive_test"
        id = Column(Integer, primary_key=True)
        mmsi = Column(String(9), nullable=False)
        ts = Column(DateTime(timezone=True), nullable=False)
        received_at = Column(DateTime(timezone=True), nullable=False)
        lat = Column(Float)
        lon = Column(Float)
        sog = Column(Float)
        cog = Column(Float)
        heading = Column(Float)
        nav_status = Column(Integer)
        source = Column(String(24))

    engine = create_engine("sqlite:///:memory:")
    base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    old = datetime.now(timezone.utc) - timedelta(days=90)
    with Session.begin() as session:
        session.add_all([
            DisposableTrack(id=i, mmsi=str(200000000 + i), ts=old,
                            received_at=old, lat=34 + i / 10000, lon=12,
                            sog=4.5, cog=90, heading=None, nav_status=0,
                            source="synthetic")
            for i in range(1, 101)
        ])

    @contextmanager
    def disposable_session_scope():
        with Session() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    objects = {}
    def put(key, payload, content_type):
        assert content_type == "application/gzip"
        objects[key] = payload

    def get(key):
        payload = objects[key]
        return payload[:-1] + bytes([payload[-1] ^ 1]) if corrupt else payload

    monkeypatch.setattr(models, "VesselTrackDB", DisposableTrack)
    monkeypatch.setattr(db_session, "session_scope", disposable_session_scope)
    monkeypatch.setattr(object_store, "put", put)
    monkeypatch.setattr(object_store, "get", get)
    monkeypatch.setattr(track_store, "_RETENTION_RELEASE_AUTHORIZED", True)
    monkeypatch.setenv("AIS_PRUNE_APPROVED", "true")
    monkeypatch.setenv("AIS_RETENTION_POLICY_ID", "synthetic-test-only")
    for field in ("OBJECT_STORAGE_ENDPOINT", "OBJECT_STORAGE_ACCESS_KEY",
                  "OBJECT_STORAGE_SECRET_KEY"):
        monkeypatch.setattr(track_store.config, field, "disposable-test")
    try:
        deleted = track_store.TrackStore().prune(older_than_days=60)
        with Session() as session:
            remaining = session.query(DisposableTrack).count()
        assert len(objects) == 1
        payload = next(iter(objects.values()))
        restored = json.loads(gzip.decompress(payload))
        assert restored["schema"] == "vessel_tracks_v1"
        assert len(restored["rows"]) == 100
        assert [row["id"] for row in restored["rows"]] == list(range(1, 101))
        assert all(set(row) == {"id", "mmsi", "ts", "received_at",
                                "lat", "lon", "sog", "cog", "heading",
                                "nav_status", "source"} for row in restored["rows"])
        assert (deleted, remaining) == ((0, 100) if corrupt else (100, 0))
    finally:
        engine.dispose()
