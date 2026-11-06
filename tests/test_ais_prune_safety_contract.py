# SPDX-License-Identifier: AGPL-3.0-or-later
"""P0 #335: fail-closed structural contract for AIS cold archival.

This is not a substitute for a two-connection PostgreSQL concurrency test.
"""
import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "apps/api/core/vessels/track_store.py"


def _prune():
    module = ast.parse(SOURCE.read_text(encoding="utf-8"))
    klass = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "TrackStore")
    return next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == "prune")


def test_prune_retention_is_release_gated_and_disabled_by_default():
    source = SOURCE.read_text(encoding="utf-8")
    assert "_RETENTION_RELEASE_AUTHORIZED = False" in source
    assert "if not _RETENTION_RELEASE_AUTHORIZED:" in ast.get_source_segment(source, _prune())


def test_prune_locks_selected_rows_and_verifies_archive_before_delete():
    """Reject accidental removal of row locks or verify-before-delete ordering."""
    source = SOURCE.read_text(encoding="utf-8")
    body = ast.get_source_segment(source, _prune())
    assert ".with_for_update(skip_locked=True)" in body
    assert body.index(".with_for_update(skip_locked=True)") < body.index("object_store.put(")
    assert body.index("object_store.put(") < body.index("object_store.get(")
    assert body.index("object_store.get(") < body.index(".delete(synchronize_session=False)")
    assert "if n != len(rows):" in body


def test_prune_requires_storage_and_explicit_policy():
    body = ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), _prune())
    assert "AIS_PRUNE_APPROVED" in body
    assert "AIS_RETENTION_POLICY_ID" in body
    assert "OBJECT_STORAGE_SECRET_KEY" in body


def test_prune_archive_and_delete_share_one_transaction_scope():
    """The row lock must remain held until delete commits, not just until PUT."""
    prune = _prune()
    scopes = [
        node for node in ast.walk(prune)
        if isinstance(node, (ast.With, ast.AsyncWith))
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "session_scope"
            for item in node.items
        )
    ]
    assert len(scopes) == 1, "Expected one transaction scope for the prune batch"
    scope = scopes[0]
    source = SOURCE.read_text(encoding="utf-8")
    body = ast.get_source_segment(source, scope)
    assert body is not None
    for required in (
        ".with_for_update(skip_locked=True)",
        "object_store.put(",
        "object_store.get(",
        "hashlib.sha256(verified).hexdigest() != digest",
        ".delete(synchronize_session=False)",
    ):
        assert required in body, f"Archive/delete escaped transaction: {required}"
    assert body.index(".with_for_update(skip_locked=True)") < body.index(".delete(synchronize_session=False)")


def test_prune_fails_closed_on_corrupt_archive_and_partial_delete():
    """Negative controls: corruption and partial deletion must abort transaction."""
    prune = _prune()
    source = SOURCE.read_text(encoding="utf-8")
    body = ast.get_source_segment(source, prune)
    assert body is not None
    # The checksum mismatch raises before the DELETE, rather than logging
    # and continuing with an unverified archive.
    assert 'raise ValueError("AIS cold archive integrity check failed")' in body
    assert body.index('raise ValueError("AIS cold archive integrity check failed")') < body.index(
        ".delete(synchronize_session=False)"
    )
    # A partial DELETE must raise inside the transaction, allowing rollback.
    assert "if n != len(rows):" in body
    assert "raise RuntimeError(" in body
    # Exceptions must not be swallowed inside the transaction scope.
    scopes = [
        n for n in ast.walk(prune)
        if isinstance(n, ast.With)
        and any(isinstance(i.context_expr, ast.Call)
                and isinstance(i.context_expr.func, ast.Name)
                and i.context_expr.func.id == "session_scope" for i in n.items)
    ]
    assert len(scopes) == 1
    assert not any(isinstance(n, ast.ExceptHandler) for n in ast.walk(scopes[0]))


def test_prune_rejects_invalid_retention_windows_before_storage_access(monkeypatch):
    """Even if a release later enables retention, zero/negative windows fail closed."""
    from typing import Optional
    import pytest

    # Avoid importing the runtime service graph: compile the actual prune method
    # with its own globals and stub only the external dependencies.
    source = SOURCE.read_text(encoding="utf-8")
    fn = _prune()
    import os
    from datetime import datetime, timedelta, timezone
    import logging
    class Config:
        VESSEL_TRACK_RETENTION_DAYS = 60
        OBJECT_STORAGE_ENDPOINT = "example"
        OBJECT_STORAGE_ACCESS_KEY = "test"
        OBJECT_STORAGE_SECRET_KEY = "test"
    namespace = {
        "__name__": "ais_prune_contract",
        "Optional": Optional,
        "os": os,
        "datetime": datetime,
        "timedelta": timedelta,
        "timezone": timezone,
        "config": Config(),
        "logger": logging.getLogger("ais_prune_contract"),
        "_RETENTION_RELEASE_AUTHORIZED": True,
    }
    method = compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), "exec")
    exec(method, namespace)
    monkeypatch.setenv("AIS_PRUNE_APPROVED", "true")
    monkeypatch.setenv("AIS_RETENTION_POLICY_ID", "test-only")
    for days in (0, -1, -365, True, 0.5):
        with pytest.raises(ValueError, match="positive integer"):
            namespace["prune"](object(), older_than_days=days)


def test_prune_invalid_configured_default_is_fail_closed(monkeypatch):
    """Negative control: a misconfigured default must never widen a prune."""
    import logging
    import os
    from datetime import datetime, timedelta, timezone
    from typing import Optional
    import pytest

    class Config:
        VESSEL_TRACK_RETENTION_DAYS = -30
        OBJECT_STORAGE_ENDPOINT = "example"
        OBJECT_STORAGE_ACCESS_KEY = "test"
        OBJECT_STORAGE_SECRET_KEY = "test"

    source = SOURCE.read_text(encoding="utf-8")
    namespace = {
        "__name__": "ais_prune_default_contract",
        "Optional": Optional,
        "os": os,
        "datetime": datetime,
        "timedelta": timedelta,
        "timezone": timezone,
        "config": Config(),
        "logger": logging.getLogger("ais_prune_default_contract"),
        "_RETENTION_RELEASE_AUTHORIZED": True,
    }
    exec(compile(ast.Module(body=[_prune()], type_ignores=[]), str(SOURCE), "exec"), namespace)
    monkeypatch.setenv("AIS_PRUNE_APPROVED", "true")
    monkeypatch.setenv("AIS_RETENTION_POLICY_ID", "test-only")
    with pytest.raises(ValueError, match="positive integer"):
        namespace["prune"](object())


def test_ais_archive_fixture_roundtrip_and_tamper_negative_control():
    """Disposable v1 archive fixture: exact rows survive gzip roundtrip.

    This is a serialization smoke test, NOT proof of R2 durability or SQL
    transaction safety. It intentionally makes no production DB/R2 calls.
    """
    import gzip
    import hashlib
    import json

    rows = [
        {
            "id": 101, "mmsi": "247000001",
            "ts": "2026-10-01T12:00:00+00:00",
            "received_at": "2026-10-01T12:00:03+00:00",
            "lat": 35.1, "lon": 12.2, "sog": 5.5, "cog": 90.0,
            "heading": 89, "nav_status": 0, "source": "fixture",
        },
        {
            "id": 102, "mmsi": "247000001",
            "ts": "2026-10-01T12:01:00+00:00",
            "received_at": "2026-10-01T12:01:02+00:00",
            "lat": 35.11, "lon": 12.21, "sog": None, "cog": None,
            "heading": None, "nav_status": None, "source": "fixture",
        },
    ]
    plain = json.dumps(
        {"schema": "vessel_tracks_v1", "rows": rows},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    compressed = gzip.compress(plain, mtime=0)
    digest = hashlib.sha256(compressed).hexdigest()
    assert gzip.compress(plain, mtime=0) == compressed
    assert hashlib.sha256(compressed).hexdigest() == digest
    restored = json.loads(gzip.decompress(compressed))
    assert restored["schema"] == "vessel_tracks_v1"
    assert restored["rows"] == rows
    assert len({r["id"] for r in restored["rows"]}) == len(rows)

    # Adversarial bit flip: checksum verification must reject the object
    # before decompression or a hypothetical DELETE.
    tampered = bytearray(compressed)
    tampered[len(tampered) // 2] ^= 0x01
    assert hashlib.sha256(tampered).hexdigest() != digest


def test_prune_archive_failure_never_reaches_delete(monkeypatch):
    """Executable fault injection against the actual prune method.

    An object-store readback failure must abort the SQL transaction before
    DELETE. This uses fake rows and sessions; no production resources.
    """
    import contextlib
    import logging
    import os
    import sys
    import types
    from datetime import datetime, timedelta, timezone
    from typing import Optional

    class Config:
        VESSEL_TRACK_RETENTION_DAYS = 60
        OBJECT_STORAGE_ENDPOINT = "fixture"
        OBJECT_STORAGE_ACCESS_KEY = "fixture"
        OBJECT_STORAGE_SECRET_KEY = "fixture"

    class Field:
        def __lt__(self, other):
            return self
        def asc(self):
            return self
        def in_(self, other):
            return self

    class Model:
        ts = Field()
        id = Field()

    class Row:
        id = 1
        mmsi = "247000001"
        ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
        received_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        lat = 35.0
        lon = 12.0
        sog = cog = heading = nav_status = None
        source = "fixture"

    events = []
    class Query:
        def filter(self, *args):
            return self
        def order_by(self, *args):
            return self
        def limit(self, *args):
            return self
        def with_for_update(self, **kwargs):
            events.append("locked")
            return self
        def all(self):
            return [Row()]
        def delete(self, **kwargs):
            events.append("DELETE")
            return 1

    class Session:
        def query(self, *args):
            return Query()

    @contextlib.contextmanager
    def session_scope():
        events.append("BEGIN")
        try:
            yield Session()
        except Exception:
            events.append("ROLLBACK")
            raise
        else:
            events.append("COMMIT")

    def put(*args):
        events.append("PUT")
    def get(*args):
        events.append("GET_FAILED")
        raise OSError("injected R2 readback outage")

    db_module = types.ModuleType("core.db")
    db_module.__path__ = []
    models_module = types.ModuleType("core.db.models")
    models_module.VesselTrackDB = Model
    session_module = types.ModuleType("core.db.session")
    session_module.session_scope = session_scope
    core_module = types.ModuleType("core")
    core_module.__path__ = []
    object_module = types.ModuleType("core.object_store")
    object_module.put = put
    object_module.get = get
    core_module.object_store = object_module
    db_module.models = models_module
    db_module.session = session_module
    for name, module in {
        "core": core_module, "core.db": db_module,
        "core.db.models": models_module, "core.db.session": session_module,
        "core.object_store": object_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    namespace = {
        "__name__": "ais_prune_fault_injection",
        "Optional": Optional, "os": os, "datetime": datetime,
        "timedelta": timedelta, "timezone": timezone,
        "config": Config(),
        "logger": logging.getLogger("ais_prune_fault_injection"),
        "_RETENTION_RELEASE_AUTHORIZED": True,
    }
    exec(compile(ast.Module(body=[_prune()], type_ignores=[]), str(SOURCE), "exec"), namespace)
    monkeypatch.setenv("AIS_PRUNE_APPROVED", "true")
    monkeypatch.setenv("AIS_RETENTION_POLICY_ID", "fixture-only")
    assert namespace["prune"](object()) == 0
    assert events == ["BEGIN", "locked", "PUT", "GET_FAILED", "ROLLBACK"]

def test_archive_integrity_failure_raises_before_delete():
    """The canonical prune source must reject a wrong readback digest.

    Static negative control complements the executable R2 outage injection;
    this does not claim a live object-store restore drill.
    """
    source = SOURCE.read_text(encoding="utf-8")
    scope = next(
        n for n in ast.walk(_prune())
        if isinstance(n, ast.With)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "session_scope"
            for item in n.items
        )
    )
    checks = [
        n for n in ast.walk(scope)
        if isinstance(n, ast.If)
        and "hashlib.sha256(verified).hexdigest() != digest"
        in (ast.get_source_segment(source, n.test) or "")
    ]
    assert len(checks) == 1, "Checksum mismatch must be checked within SQL transaction"
    assert any(isinstance(n, ast.Raise) for n in ast.walk(checks[0])), (
        "Checksum mismatch must abort transaction before SQL DELETE"
    )
