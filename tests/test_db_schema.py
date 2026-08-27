# SPDX-License-Identifier: AGPL-3.0-or-later
"""Additive-column backfill for deployments without a migration framework."""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from core.db.session import _ADDITIVE_COLUMNS, _ensure_additive_columns


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
