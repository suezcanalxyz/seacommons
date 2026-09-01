# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md F-14 / Phase 2.2 -- recent-event composite indexes.

The hot persisted_events() query shapes must use a composite index, not a
full-table scan.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from core.db.models import Base


def _fresh_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'plans.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for i in range(50):
            conn.execute(
                text(
                    "INSERT INTO intel_events "
                    "(id, timestamp_utc, type, severity, title, source, schema_version) "
                    "VALUES (:id, :ts, :type, 'high', 't', :src, 1)"
                ),
                {
                    "id": f"e{i}",
                    "ts": f"2026-08-{(i % 28) + 1:02d}T00:00:00+00:00",
                    "type": "twitter" if i % 2 else "distress",
                    "src": "Alarm Phone" if i % 3 else "Sea-Watch",
                },
            )
    return engine


def _plan(engine, sql: str, params: dict) -> str:
    with engine.connect() as conn:
        rows = conn.execute(text(f"EXPLAIN QUERY PLAN {sql}"), params).fetchall()
    return " | ".join(str(r[-1]) for r in rows)


def test_composite_indexes_exist(tmp_path):
    names = {idx["name"] for idx in inspect(_fresh_engine(tmp_path)).get_indexes("intel_events")}
    assert "ix_intel_events_source_ts" in names
    assert "ix_intel_events_type_ts" in names


def test_source_time_window_query_uses_the_composite_index(tmp_path):
    engine = _fresh_engine(tmp_path)
    plan = _plan(
        engine,
        "SELECT * FROM intel_events WHERE timestamp_utc >= :cut AND source = :src "
        "ORDER BY timestamp_utc DESC LIMIT 100",
        {"cut": "2026-08-01T00:00:00+00:00", "src": "Alarm Phone"},
    )
    assert "ix_intel_events_source_ts" in plan
    assert "SCAN intel_events" not in plan  # no full-table scan


def test_type_time_window_query_uses_the_composite_index(tmp_path):
    engine = _fresh_engine(tmp_path)
    plan = _plan(
        engine,
        "SELECT * FROM intel_events WHERE timestamp_utc >= :cut AND type IN ('twitter') "
        "ORDER BY timestamp_utc DESC LIMIT 100",
        {"cut": "2026-08-01T00:00:00+00:00"},
    )
    assert "ix_intel_events_type_ts" in plan
