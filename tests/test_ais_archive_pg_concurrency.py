# SPDX-License-Identifier: AGPL-3.0-or-later
"""#335: real PostgreSQL two-connection archive-lock adversarial probe.

Run only against an explicitly provisioned DISPOSABLE PostgreSQL test database:
  AIS_ARCHIVE_TEST_DATABASE_URL=postgresql+psycopg://... \
  AIS_ARCHIVE_DISPOSABLE_DB_ACK=YES pytest -q tests/test_ais_archive_pg_concurrency.py

No production data, object store, retention switch or existing tables are touched.
"""
import os
import uuid
import gzip
import hashlib
import json

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine, event, text
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
    # Capture every SQL statement on this connection pool. The wrong-DB
    # negative control must prove absence of DDL, not just absence of tables.
    issued_ddl = []

    @event.listens_for(engine, "before_cursor_execute")
    def record_ddl(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("CREATE ", "ALTER ", "DROP ", "TRUNCATE ")):
            issued_ddl.append(statement)

    identity_verified = False
    table_created = False
    try:
        # Fail before any DDL if the DSN resolves to another database.
        with engine.connect() as identity:
            actual_db = identity.execute(text("SELECT current_database()")).scalar_one()
            assert actual_db == expected_db, (
                f"Refusing probe DDL: connected database {actual_db!r} != expected {expected_db!r}"
            )
        identity_verified = True
        with engine.begin() as setup:
            setup.execute(text(f"CREATE TABLE {table} (id integer PRIMARY KEY, ts integer, lat integer)"))
            table_created = True
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
                # Negative control: a nonlocked eligible row must still be selected.
                # Otherwise a broken query that returns nothing could falsely pass.
                with engine.begin() as insert_other:
                    insert_other.execute(text(f"INSERT INTO {table} VALUES (3, 2, 30)"))
                with engine.connect() as reader:
                    with reader.begin():
                        other = reader.execute(text(
                            f"SELECT id FROM {table} WHERE ts < 10 ORDER BY id FOR UPDATE SKIP LOCKED"
                        )).scalars().all()
                        assert other == [3]
                # Positive concurrency control: the archive row lock must not
                # block a writer updating a different, eligible unlocked row.
                # This distinguishes row-level protection from accidental
                # table-wide serialization that could stall live AIS ingest.
                with engine.begin() as independent_writer:
                    independent_writer.execute(text("SET LOCAL lock_timeout = '200ms'"))
                    changed = independent_writer.execute(text(
                        f"UPDATE {table} SET lat = 31 WHERE id = 3"
                    ))
                    assert changed.rowcount == 1
                with engine.connect() as independent_verify:
                    assert independent_verify.execute(text(
                        f"SELECT lat FROM {table} WHERE id = 3"
                    )).scalar_one() == 31
                # Simulate archive verification failure: do not delete; rollback.
                tx_archive.rollback()
            finally:
                if tx_archive.is_active:
                    tx_archive.rollback()
        # Negative control: the aborted archive must preserve the original row.
        with engine.connect() as verify:
            rows_after_abort = verify.execute(text(
                f"SELECT id, ts, lat FROM {table} ORDER BY id"
            )).all()
            assert rows_after_abort == [
                (1, 1, 10),  # failed archival transaction preserved the locked row
                (2, 20, 20), # ineligible observation remains untouched
                (3, 2, 31),  # independent committed writer survives archive rollback
            ]
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
        # Negative control: DELETE followed by failed archive commit must roll back.
        with engine.connect() as aborted_delete:
            transaction = aborted_delete.begin()
            try:
                locked = aborted_delete.execute(text(
                    f"SELECT id, ts, lat FROM {table} WHERE id = 1 FOR UPDATE"
                )).mappings().all()
                assert [dict(row) for row in locked] == [{"id": 1, "ts": 1, "lat": 11}]
                assert aborted_delete.execute(text(
                    f"DELETE FROM {table} WHERE id = 1"
                )).rowcount == 1
                assert aborted_delete.execute(text(
                    f"SELECT count(*) FROM {table} WHERE id = 1"
                )).scalar_one() == 0
                transaction.rollback()  # injected failure before COMMIT
            finally:
                if transaction.is_active:
                    transaction.rollback()
        with engine.connect() as verify_abort:
            assert [dict(row) for row in verify_abort.execute(text(
                f"SELECT id, ts, lat FROM {table} WHERE id = 1"
            )).mappings().all()] == [{"id": 1, "ts": 1, "lat": 11}]
            assert verify_abort.execute(text(
                f"SELECT lat FROM {table} WHERE id = 3"
            )).scalar_one() == 31
        # Positive transaction control: the same locked row can be archived,
        # deleted and restored without altering independently committed rows.
        # This is an in-memory serialization probe, NOT S3/R2 durability proof.
        with engine.begin() as archive_commit:
            archived = [dict(row) for row in archive_commit.execute(text(
                f"SELECT id, ts, lat FROM {table} WHERE id = 1 FOR UPDATE"
            )).mappings().all()]
            assert archived == [{"id": 1, "ts": 1, "lat": 11}]
            deleted = archive_commit.execute(text(f"DELETE FROM {table} WHERE id = 1"))
            assert deleted.rowcount == len(archived) == 1
        with engine.connect() as verify_deleted:
            assert verify_deleted.execute(text(
                f"SELECT count(*) FROM {table} WHERE id = 1"
            )).scalar_one() == 0
        # Roundtrip the committed PostgreSQL snapshot through compressed evidence.
        # This still does not prove S3/R2 durability.
        archive_bytes = gzip.compress(
            json.dumps({"schema": "ais_pg_probe_v1", "rows": archived},
                       sort_keys=True, separators=(",", ":")).encode("utf-8"),
            mtime=0,
        )
        archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
        # Restore must validate the stored digest *before* decompression or SQL.
        # Merely asserting that corruption changes a digest does not enforce
        # the fail-closed restore boundary.
        def verified_archive_payload(blob, expected_digest):
            if hashlib.sha256(blob).hexdigest() != expected_digest:
                raise ValueError("AIS archive checksum mismatch")
            # Bound decompression before JSON parsing.
            import io
            max_expanded_bytes = 1024 * 1024  # disposable probe only
            with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as stream:
                expanded = stream.read(max_expanded_bytes + 1)
                if len(expanded) > max_expanded_bytes:
                    raise ValueError("AIS archive expanded size limit exceeded")
            payload = json.loads(expanded)
            if not isinstance(payload, dict) or payload.get("schema") != "ais_pg_probe_v1":
                raise ValueError("AIS archive schema mismatch")
            rows = payload.get("rows")
            if not isinstance(rows, list) or not rows or any(
                not isinstance(row, dict)
                or set(row) != {"id", "ts", "lat"}
                or any(type(row[key]) is not int for key in ("id", "ts", "lat"))
                for row in rows
            ):
                raise ValueError("AIS archive row contract mismatch")
            if len({row["id"] for row in rows}) != len(rows):
                raise ValueError("AIS archive duplicate observation ID")
            return payload

        corrupted = bytearray(archive_bytes)
        corrupted[len(corrupted) // 2] ^= 1
        with pytest.raises(ValueError, match="checksum mismatch"):
            verified_archive_payload(bytes(corrupted), archive_sha256)
        # A digest-valid but incompatible schema must also be rejected.
        wrong_schema = gzip.compress(
            json.dumps({"schema": "unknown", "rows": archived}).encode("utf-8"),
            mtime=0,
        )
        with pytest.raises(ValueError, match="schema mismatch"):
            verified_archive_payload(
                wrong_schema, hashlib.sha256(wrong_schema).hexdigest()
            )
        # A checksum-valid compressed payload can expand beyond a safe limit.
        oversized = gzip.compress(
            json.dumps({"schema": "ais_pg_probe_v1", "rows": archived,
                        "padding": "x" * (1024 * 1024 + 1)}).encode("utf-8"),
            mtime=0,
        )
        with pytest.raises(ValueError, match="expanded size limit exceeded"):
            verified_archive_payload(
                oversized, hashlib.sha256(oversized).hexdigest()
            )
        # Valid checksums and schema labels do not imply valid observations.
        # Reject malformed and duplicate rows before any SQL is issued.
        for bad_rows, expected_error in [
            ({"id": 1, "ts": 1, "lat": 11}, "row contract mismatch"),
            ([{"id": 1, "ts": 1, "lat": "11"}], "row contract mismatch"),
            ([{"id": 1, "ts": 1, "lat": 11, "extra": 9}], "row contract mismatch"),
            ([archived[0], archived[0]], "duplicate observation ID"),
        ]:
            bad_blob = gzip.compress(json.dumps({
                "schema": "ais_pg_probe_v1", "rows": bad_rows
            }).encode("utf-8"), mtime=0)
            with pytest.raises(ValueError, match=expected_error):
                verified_archive_payload(bad_blob, hashlib.sha256(bad_blob).hexdigest())
        # Both negative controls run while the archived row is absent:
        # neither failure may reinsert or modify a database observation.
        with engine.connect() as before_restore:
            assert before_restore.execute(text(
                f"SELECT count(*) FROM {table} WHERE id = 1"
            )).scalar_one() == 0
        restored_payload = verified_archive_payload(archive_bytes, archive_sha256)
        assert restored_payload["rows"] == archived
        with engine.begin() as restore:
            restore.execute(text(
                f"INSERT INTO {table} (id, ts, lat) VALUES (:id, :ts, :lat)"
            ), restored_payload["rows"])
        with engine.connect() as verify_restored:
            assert [dict(row) for row in verify_restored.execute(text(
                f"SELECT id, ts, lat FROM {table} ORDER BY id"
            )).mappings().all()] == [
                {"id": 1, "ts": 1, "lat": 11},
                {"id": 2, "ts": 20, "lat": 20},
                {"id": 3, "ts": 2, "lat": 31},
            ]
    finally:
        try:
            # Never issue DDL after a failed identity guard, including cleanup.
            # A failed CREATE must likewise not trigger a DROP against an
            # unrelated object in a wrongly configured environment.
            if identity_verified and table_created:
                with engine.begin() as cleanup:
                    cleanup.execute(text(f"DROP TABLE IF EXISTS {table}"))
        finally:
            engine.dispose()
            if not identity_verified:
                assert not issued_ddl, (
                    f"Identity rejection issued forbidden DDL: {issued_ddl!r}"
                )
