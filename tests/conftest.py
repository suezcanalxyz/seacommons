from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

_TEST_DATABASE = Path(tempfile.gettempdir()) / f"seacommons_pytest_{uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE.as_posix()}"
os.environ["RUNTIME_PROFILE"] = "operational"
# The production checkout may be tested from a shell that inherits service
# configuration.  Keep the suite hermetic: tests must never authenticate to,
# read from, or write to live infrastructure unless a test opts in explicitly.
for _production_setting in (
    "DRIFT_WORKER_URL",
    "DRIFT_WORKER_SECRET",
    "TWIKIT_ENABLED",
    "TWIKIT_COOKIES_FILE",
    "OBJECT_STORAGE_ENDPOINT",
    "OBJECT_STORAGE_ACCESS_KEY",
    "OBJECT_STORAGE_SECRET_KEY",
    "AISSTREAM_KEY",
    "AISSTREAM_NGO_KEY",
):
    os.environ[_production_setting] = "false" if _production_setting == "TWIKIT_ENABLED" else ""
# Never let a pytest process start production monitors just because the shell
# inherited the VM service environment. Individual bootstrap tests explicitly
# invoke/mocks the component they exercise.
os.environ["INTEL_MONITORS_ENABLED"] = "false"
os.environ["SEACOMMONS_FORENSIC_SYNC"] = "true"
os.environ["SEACOMMONS_TRACK_STORE_SYNC"] = "1"
os.environ["SEACOMMONS_INTEL_PERSIST_SYNC"] = "true"


def pytest_sessionstart(session) -> None:
    """Create an isolated schema before test modules import the application."""
    from core.db.session import init_database

    init_database()


@pytest.fixture(autouse=True)
def _disable_background_api_sync(monkeypatch) -> None:
    """Do not leave a DB-sync daemon running after TestClient lifespan tests."""
    monkeypatch.setattr("core.api.main._start_intel_sync_loop", lambda: None)


@pytest.fixture(autouse=True)
def _landmask_off(monkeypatch) -> None:
    """Use a deterministic sea classifier without loading coastline data in CI.

    The production drift gate fails closed when the landmask returns ``None``.
    Defaulting every test to ``None`` therefore makes otherwise valid
    at-sea fixtures ineligible, obscuring the behavior under test. Model
    ordinary test points as sea (``False``) instead; this also keeps
    ``nearest_sea_point`` a pass-through without loading roaring_landmask.
    Land, unavailable, and exception paths MUST explicitly override
    ``is_on_land`` in their own tests (see test_auto_drift_eligibility).
    This is test-only and never changes production classification.
    """
    monkeypatch.setattr("core.intel.landmask.is_on_land", lambda lat, lon: False)


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
