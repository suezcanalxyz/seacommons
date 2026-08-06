from __future__ import annotations

import os
import tempfile
from pathlib import Path


_TEST_DATABASE = Path(tempfile.gettempdir()) / f"seacommons_pytest_{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE.as_posix()}"
os.environ.setdefault("RUNTIME_PROFILE", "operational")
os.environ["SEACOMMONS_FORENSIC_SYNC"] = "true"


def pytest_sessionstart(session) -> None:
    """Create an isolated schema before test modules import the application."""
    from core.db.session import init_database

    init_database()


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
