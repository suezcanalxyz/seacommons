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
    import sys
    import types
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
