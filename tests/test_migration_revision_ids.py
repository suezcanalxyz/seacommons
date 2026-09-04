from __future__ import annotations

import ast
from pathlib import Path


def _revision_id(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "revision" for t in node.targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    raise AssertionError(f"No revision id found in {path}")


def test_alembic_revision_ids_fit_default_version_table() -> None:
    versions = Path("apps/api/core/db/migrations/versions")
    offenders = {
        path.name: revision
        for path in sorted(versions.glob("*.py"))
        if (revision := _revision_id(path)) and len(revision) > 32
    }
    assert offenders == {}
