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

_DEFAULT_SQLITE = "sqlite:///./core/data/suezcanal_pilot.db"


def database_url() -> str:
    raw = os.getenv("DATABASE_URL") or config.DATABASE_URL or _DEFAULT_SQLITE
    if raw.startswith("postgresql://") and "localhost" in raw and not os.getenv("DATABASE_URL"):
        return _DEFAULT_SQLITE
    return raw


@lru_cache(maxsize=1)
def engine():
    url = database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)


@lru_cache(maxsize=1)
def session_factory():
    return sessionmaker(bind=engine(), autoflush=False, autocommit=False, future=True)


def init_database() -> None:
    Path("core/data").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine())


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
