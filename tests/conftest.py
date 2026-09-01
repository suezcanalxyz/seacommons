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
def _landmask_off(monkeypatch) -> None:
    """Default the sea-snap landmask to "unavailable" for every test.

    ``roaring_landmask`` is a heavy optional dependency (it ships with the
    drift stack, not with a minimal CI image). With it absent, ``is_on_land``
    returns ``None`` and ``nearest_sea_point`` is a pure pass-through — which
    is what most tests want: they assert an exact parsed/stored coordinate and
    are not about sea-snapping. Tests that DO exercise the snap re-patch
    ``core.intel.landmask.is_on_land`` themselves. Patching it here is enough:
    ``nearest_sea_point`` consults ``is_on_land`` internally and short-circuits
    to a pass-through when it returns ``None``, regardless of how callers
    imported it.
    """
    monkeypatch.setattr("core.intel.landmask.is_on_land", lambda lat, lon: None)


@pytest.fixture(autouse=True)
def _reset_media_ocr_queue() -> None:
    """Drop the shared bounded OCR pool's backlog between tests."""
    from core.intel.media_ocr_queue import media_ocr_queue

    media_ocr_queue.reset()
    yield
    media_ocr_queue.reset()


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
