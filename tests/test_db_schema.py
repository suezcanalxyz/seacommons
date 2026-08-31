# SPDX-License-Identifier: AGPL-3.0-or-later
"""Additive-column/index backfill for deployments without a migration framework."""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from core.db.models import Base
from core.db.session import _ADDITIVE_COLUMNS, _ensure_additive_columns, _ensure_indexes


def test_ensure_additive_columns_backfills_a_missing_column(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'schema.db'}")

    # A database created before case_type existed.
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE cases (case_id VARCHAR(36) PRIMARY KEY, title VARCHAR(256))"))
    assert "case_type" not in {c["name"] for c in inspect(eng).get_columns("cases")}

    _ensure_additive_columns(eng)
    assert "case_type" in {c["name"] for c in inspect(eng).get_columns("cases")}

    # Idempotent over an already-migrated table.
    _ensure_additive_columns(eng)


def test_ensure_additive_columns_skips_absent_tables(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    _ensure_additive_columns(eng)  # must not raise when the table is absent


def test_additive_columns_are_declared_not_null_or_defaulted():
    # Every entry must be safe to ALTER onto a populated table.
    for _table, _column, ddl in _ADDITIVE_COLUMNS:
        assert "NOT NULL" not in ddl.upper() or "DEFAULT" in ddl.upper()


def test_ensure_indexes_backfills_a_missing_index_on_a_preexisting_table(tmp_path):
    """Real production case: intel_events had zero indexes despite three
    index=True model columns (timestamp_utc/type/severity) -- create_all()
    only creates indexes for a table it creates fresh, never retrofits one
    that already existed. Every persisted_events() call was a full 33k-row
    scan, twice per Live poll, occasionally slow enough to trip the
    frontend's fetch timeout and blank the public map."""
    eng = create_engine(f"sqlite:///{tmp_path / 'schema.db'}")

    # A pre-existing intel_events table from before timestamp_utc/type/
    # severity gained index=True -- same shape as the real production gap,
    # created without going through Base.metadata.create_all().
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE intel_events ("
            "id VARCHAR(16) PRIMARY KEY, timestamp_utc VARCHAR(32) NOT NULL, "
            "type VARCHAR(32) NOT NULL, severity VARCHAR(16) NOT NULL, "
            "lat FLOAT, lon FLOAT, title VARCHAR(256) NOT NULL, text TEXT, "
            "url VARCHAR(512), source VARCHAR(64) NOT NULL, "
            "linked_mmsi VARCHAR(16), meta JSON, created_at DATETIME)"
        ))
    assert inspect(eng).get_indexes("intel_events") == []

    _ensure_indexes(eng)

    indexed_columns = {
        col
        for idx in inspect(eng).get_indexes("intel_events")
        for col in idx["column_names"]
    }
    assert {"timestamp_utc", "type", "severity", "source"} <= indexed_columns

    # Idempotent over an already-migrated table.
    _ensure_indexes(eng)


def test_ensure_indexes_skips_absent_tables(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    _ensure_indexes(eng)  # must not raise when no declared table exists yet


def test_ensure_indexes_does_not_touch_a_freshly_created_table(tmp_path):
    """create_all() already gives a brand-new table every declared index --
    _ensure_indexes only needs to backfill a table that predates the model."""
    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(bind=eng)
    before = inspect(eng).get_indexes("intel_events")
    _ensure_indexes(eng)
    after = inspect(eng).get_indexes("intel_events")
    assert len(before) == len(after)
