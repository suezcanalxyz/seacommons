# SPDX-License-Identifier: AGPL-3.0-or-later
"""Database bootstrap helpers for pilot mode."""
from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import config
from core.db.models import Base

# Anchor the default SQLite path to the apps/api directory regardless of CWD.
# __file__ = apps/api/core/db/session.py → parents[2] = apps/api/
_API_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SQLITE = f"sqlite:///{_API_ROOT}/core/data/suezcanal_pilot.db"


def database_url() -> str:
    raw = os.getenv("DATABASE_URL") or config.DATABASE_URL or _DEFAULT_SQLITE
    if raw.startswith("postgresql://") and "localhost" in raw and not os.getenv("DATABASE_URL"):
        return _DEFAULT_SQLITE
    return raw


@lru_cache(maxsize=1)
def engine():
    url = database_url()
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    else:
        # pool_pre_ping only catches a connection that's already dead; it does
        # nothing for one that's alive but stuck (e.g. a server-side restart
        # or network blip mid-query). Without a hard cap, a single long-lived
        # background loop (like live_edge_publisher's 1s poll) can hang on
        # one bad query forever with no exception to recover from — verified
        # live: the publisher froze silently for 46+ minutes, serving a
        # stale snapshot to the public map the whole time, with systemd still
        # reporting it as healthy since the process never actually exited.
        connect_args = {"connect_timeout": 10, "options": "-c statement_timeout=20000"}
    return create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)


@lru_cache(maxsize=1)
def session_factory():
    return sessionmaker(bind=engine(), autoflush=False, autocommit=False, future=True)


# Additive column backfill for deployments that predate a model change.
# This project has no migration framework: create_all() adds missing tables
# but never alters an existing one. Every entry here must be a nullable or
# server-defaulted ADD COLUMN that is safe to apply repeatedly; the DDL form
# below is accepted by both SQLite and PostgreSQL.
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("cases", "case_type", "VARCHAR(32) NOT NULL DEFAULT 'distress_sar'"),
]


def _ensure_additive_columns(eng=None) -> None:
    from sqlalchemy import inspect, text

    eng = eng or engine()
    inspector = inspect(eng)
    tables = set(inspector.get_table_names())
    with eng.begin() as conn:
        for table, column, ddl in _ADDITIVE_COLUMNS:
            if table not in tables:
                continue
            if column in {col["name"] for col in inspector.get_columns(table)}:
                continue
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {column} {ddl}'))


def init_database() -> None:
    (_API_ROOT / "core" / "data").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine())
    _ensure_additive_columns()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
