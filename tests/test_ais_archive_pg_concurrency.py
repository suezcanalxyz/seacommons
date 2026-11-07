# SPDX-License-Identifier: AGPL-3.0-or-later
"""#335: real PostgreSQL two-connection archive-lock adversarial probe.

Run only against an explicitly provisioned DISPOSABLE PostgreSQL test database:
  AIS_ARCHIVE_TEST_DATABASE_URL=postgresql+psycopg://... \
  AIS_ARCHIVE_DISPOSABLE_DB_ACK=YES pytest -q tests/test_ais_archive_pg_concurrency.py

No production data, object store, retention switch or existing tables are touched.
"""
import os
import uuid

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


def test_locked_archive_row_cannot_be_updated_or_deleted_concurrently():
    url = os.getenv("AIS_ARCHIVE_TEST_DATABASE_URL", "")
    if not url or os.getenv("AIS_ARCHIVE_DISPOSABLE_DB_ACK") != "YES":
        pytest.skip("Requires explicitly acknowledged disposable PostgreSQL database")
    if not url.startswith(("postgresql+psycopg://", "postgresql+psycopg2://")):
        pytest.fail("Only explicit PostgreSQL test URLs are supported")
    # The test creates and drops only its own randomized table; never reuse a
    # production connection string. An explicit acknowledgment is mandatory.
    expected_db = os.getenv("AIS_ARCHIVE_EXPECTED_DATABASE", "")
    if not expected_db or expected_db.lower() in {"postgres", "template0", "template1"}:
        pytest.fail("Set AIS_ARCHIVE_EXPECTED_DATABASE to a dedicated disposable database name")
    table = "ais_archive_probe_" + uuid.uuid4().hex[:16]
    engine = create_engine(url, pool_size=2, max_overflow=1)
    try:
        # Fail before any DDL if the DSN resolves to another database.
        with engine.connect() as identity:
            actual_db = identity.execute(text("SELECT current_database()")).scalar_one()
            assert actual_db == expected_db, (
                f"Refusing probe DDL: connected database {actual_db!r} != expected {expected_db!r}"
            )
        with engine.begin() as setup:
            setup.execute(text(f"CREATE TABLE {table} (id integer PRIMARY KEY, ts integer, lat integer)"))
            setup.execute(text(f"INSERT INTO {table} VALUES (1, 1, 10), (2, 20, 20)"))
        with engine.connect() as archivist, engine.connect() as writer:
            tx_archive = archivist.begin()
            try:
                selected = archivist.execute(text(
                    f"SELECT id, ts, lat FROM {table} WHERE ts < 10 "
                    "ORDER BY id FOR UPDATE SKIP LOCKED"
                )).mappings().all()
                assert [dict(r) for r in selected] == [{"id": 1, "ts": 1, "lat": 10}]
                tx_writer = writer.begin()
                try:
                    writer.execute(text("SET LOCAL lock_timeout = '200ms'"))
                    with pytest.raises(DBAPIError) as blocked_update:
                        writer.execute(text(f"UPDATE {table} SET lat = 99 WHERE id = 1"))
                    assert getattr(blocked_update.value.orig, "sqlstate", None) == "55P03" or getattr(blocked_update.value.orig, "pgcode", None) == "55P03"
                finally:
                    tx_writer.rollback()
                # Negative control: a concurrent DELETE must also be blocked,
                # otherwise a competing cleanup could remove unarchived evidence.
                tx_delete = writer.begin()
                try:
                    writer.execute(text("SET LOCAL lock_timeout = '200ms'"))
                    with pytest.raises(DBAPIError) as blocked_delete:
                        writer.execute(text(f"DELETE FROM {table} WHERE id = 1"))
                    assert getattr(blocked_delete.value.orig, "sqlstate", None) == "55P03" or getattr(blocked_delete.value.orig, "pgcode", None) == "55P03"
                finally:
                    tx_delete.rollback()
                # A second reader using SKIP LOCKED must not archive the same row.
                with engine.connect() as reader:
                    with reader.begin():
                        other = reader.execute(text(
                            f"SELECT id FROM {table} WHERE ts < 10 FOR UPDATE SKIP LOCKED"
                        )).all()
                        assert other == []  # Row 1 is locked; row 2 is outside the archival cutoff.
                # Negative control: a nonlocked eligible row must still be selected.\n                # Otherwise a broken query that returns nothing could falsely pass.\n                with engine.begin() as insert_other:\n                    insert_other.execute(text(f"INSERT INTO {table} VALUES (3, 2, 30)"))\n                with engine.connect() as reader:\n                    with reader.begin():\n                        other = reader.execute(text(\n                            f"SELECT id FROM {table} WHERE ts < 10 ORDER BY id FOR UPDATE SKIP LOCKED"\n                        )).scalars().all()\n                        assert other == [3]\n                # Simulate archive verification failure: do not delete; rollback.
                tx_archive.rollback()
            finally:
                if tx_archive.is_active:
                    tx_archive.rollback()
        # Negative control: the aborted archive must preserve the original row.
        with engine.connect() as verify:
            assert verify.execute(text(f"SELECT lat FROM {table} WHERE id = 1")).scalar_one() == 10
        # Positive control: after rollback releases the row lock, a real writer
        # must be able to commit an update (not merely time out forever).
        with engine.begin() as resumed_writer:
            resumed_writer.execute(text("SET LOCAL lock_timeout = '200ms'"))
            updated = resumed_writer.execute(
                text(f"UPDATE {table} SET lat = 11 WHERE id = 1")
            )
            assert updated.rowcount == 1
        with engine.connect() as verify:
            assert verify.execute(text(f"SELECT lat FROM {table} WHERE id = 1")).scalar_one() == 11
    finally:
        try:
            with engine.begin() as cleanup:
                cleanup.execute(text(f"DROP TABLE IF EXISTS {table}"))
        finally:
            engine.dispose()
