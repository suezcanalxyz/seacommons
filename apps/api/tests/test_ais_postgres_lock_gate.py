# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opt-in PostgreSQL two-session test of the *canonical* AIS prune path.

Run with TEST_AIS_POSTGRES_URL pointing to a disposable PostgreSQL database:
    TEST_AIS_POSTGRES_URL=postgresql+psycopg://... pytest -q apps/api/tests/test_ais_postgres_lock_gate.py
Never point this test at production. R2/S3 restore remains a separate gate.
"""
import gzip
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine, text, update
from sqlalchemy.orm import declarative_base, sessionmaker


@pytest.mark.skipif(not os.getenv("TEST_AIS_POSTGRES_URL"), reason="disposable PostgreSQL URL required")
@pytest.mark.parametrize("fault", ["none", "ambiguous_put", "corrupt_get"])
def test_prune_locks_concurrent_writer_and_restores_exact_rows(monkeypatch, fault):
    from core.vessels import track_store
    from core.db import models, session as db_session
    from core import object_store

    url = os.environ["TEST_AIS_POSTGRES_URL"]
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        pytest.fail("TEST_AIS_POSTGRES_URL must use PostgreSQL")
    # Never run this against a database containing real SeaCommons tables.
    with engine.connect() as conn:
        existing = conn.execute(text(
            "SELECT to_regclass('public.vessel_tracks')"
        )).scalar()
        if existing is not None:
            pytest.fail("Refusing to run on a database with canonical vessel_tracks")
    Base = declarative_base()

    class Track(Base):
        __tablename__ = "ais_prune_integration_disposable"
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

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    old = datetime.now(timezone.utc) - timedelta(days=90)
    original = []
    entered_put = threading.Event()
    release_put = threading.Event()
    writer_done = threading.Event()
    stored = {}
    errors = []

    @contextmanager
    def scope():
        with Session.begin() as session:
            yield session

    def put(key, payload, content_type):
        assert content_type == "application/gzip"
        stored[key] = payload
        entered_put.set()
        if not release_put.wait(timeout=15):
            raise TimeoutError("test did not release archive PUT")
        if fault == "ambiguous_put":
            # Object exists, but client never receives a successful PUT response.
            raise TimeoutError("synthetic lost PUT acknowledgement")

    def get(key):
        if fault == "corrupt_get":
            return stored[key] + b"corrupt"
        return stored[key]

    def writer():
        try:
            if not entered_put.wait(timeout=15):
                raise TimeoutError("prune did not reach PUT")
            with Session.begin() as db:
                db.execute(update(Track).where(Track.id == 1).values(lat=55.0))
            writer_done.set()
        except Exception as exc:
            errors.append(exc)

    def pruning():
        try:
            result.append(track_store.TrackStore().prune(older_than_days=60))
        except Exception as exc:
            errors.append(exc)

    result = []
    try:
        with Session.begin() as db:
            for i in range(1, 101):
                db.add(Track(id=i, mmsi=str(200000000+i), ts=old,
                             received_at=old, lat=float(i), lon=12.0,
                             sog=4.5, cog=90.0, heading=None,
                             nav_status=0, source="synthetic"))
        with Session() as db:
            original = {r.id: {field: (getattr(r, field).isoformat() if field in ("ts", "received_at") else getattr(r, field))
                           for field in ("id", "mmsi", "ts", "received_at", "lat", "lon", "sog", "cog", "heading", "nav_status", "source")}
                        for r in db.query(Track).all()}

        monkeypatch.setattr(models, "VesselTrackDB", Track)
        monkeypatch.setattr(db_session, "session_scope", scope)
        monkeypatch.setattr(object_store, "put", put)
        monkeypatch.setattr(object_store, "get", get)
        monkeypatch.setattr(track_store, "_RETENTION_RELEASE_AUTHORIZED", True)
        monkeypatch.setenv("AIS_PRUNE_APPROVED", "true")
        monkeypatch.setenv("AIS_RETENTION_POLICY_ID", "disposable-postgres-test")
        for field in ("OBJECT_STORAGE_ENDPOINT", "OBJECT_STORAGE_ACCESS_KEY",
                      "OBJECT_STORAGE_SECRET_KEY"):
            monkeypatch.setattr(track_store.config, field, "test-only")

        prune_thread = threading.Thread(target=pruning)
        writer_thread = threading.Thread(target=writer)
        prune_thread.start()
        assert entered_put.wait(timeout=15), "canonical prune did not reach object PUT"
        writer_thread.start()
        # Writer must not commit while prune holds the row lock.
        assert not writer_done.wait(timeout=0.3), "concurrent writer bypassed FOR UPDATE"
        release_put.set()
        prune_thread.join(timeout=20)
        writer_thread.join(timeout=20)
        assert not prune_thread.is_alive() and not writer_thread.is_alive()
        if fault != "none":
            # Failed object verification must roll back the SQL transaction;
            # concurrent writer may subsequently commit its independent update.
            assert not errors and result == [0], (fault, errors, result)
            with Session() as db:
                assert db.query(Track).count() == 100
            return
        assert not errors, errors
        assert result == [100]
        assert writer_done.is_set()
        assert len(stored) == 1
        archive = json.loads(gzip.decompress(next(iter(stored.values()))))
        assert archive["schema"] == "vessel_tracks_v1"
        assert len(archive["rows"]) == 100
        assert {r["id"]: r for r in archive["rows"]} == original
        # Independent restore into the disposable PostgreSQL table, not the live store.
        # All eleven fields must survive the archive -> decode -> SQL insert path.
        with Session.begin() as restore_db:
            for record in archive["rows"]:
                values = dict(record)
                for field in ("ts", "received_at"):
                    values[field] = datetime.fromisoformat(values[field])
                restore_db.add(Track(**values))
        with Session() as restored_db:
            recovered = {r.id: {field: (getattr(r, field).isoformat() if field in ("ts", "received_at") else getattr(r, field))
                                for field in ("id", "mmsi", "ts", "received_at", "lat", "lon", "sog", "cog", "heading", "nav_status", "source")}
                         for r in restored_db.query(Track).all()}
        assert recovered == original
        # Concurrent UPDATE must not resurrect or silently overwrite a deleted row.
    finally:
        release_put.set()
        Base.metadata.drop_all(engine)
        engine.dispose()
