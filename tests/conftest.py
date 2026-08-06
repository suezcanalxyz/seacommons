from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest


_TEST_DATABASE = Path(tempfile.gettempdir()) / f"seacommons_pytest_{uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE.as_posix()}"
os.environ.setdefault("RUNTIME_PROFILE", "operational")
os.environ["SEACOMMONS_FORENSIC_SYNC"] = "true"
os.environ["SEACOMMONS_INTEL_PERSIST_SYNC"] = "true"


def pytest_sessionstart(session) -> None:
    """Create an isolated schema before test modules import the application."""
    from core.db.session import init_database

    init_database()


@pytest.fixture(autouse=True)
def isolated_database() -> None:
    """Give every test empty tables and prevent cross-test DB state."""
    from core.db.models import Base
    from core.db.session import engine

    active_engine = engine()
    with active_engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    yield


def pytest_sessionfinish(session, exitstatus) -> None:
    """Dispose SQLite handles and remove only this session's temporary DB."""
    from core.db.session import engine

    engine().dispose()
    try:
        _TEST_DATABASE.unlink(missing_ok=True)
    except PermissionError:
        # Defensive fallback for a third-party SQLite handle still closing on
        # Windows. The per-process filename keeps the next run isolated.
        pass
