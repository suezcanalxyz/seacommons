#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

_HTTPX = frozenset({"get", "post", "put", "delete", "patch", "request", "Client", "AsyncClient"})
_REQUESTS = frozenset({"get", "post", "put", "delete", "patch", "request", "Session"})


def _display_path(path: Path) -> str:
    parts = path.as_posix().split("/")
    try:
        index = parts.index("apps")
    except ValueError:
        return path.as_posix()
    return "/".join(parts[index:])


class _CallScanner(ast.NodeVisitor):
    def __init__(self) -> None:
        self.module_aliases: dict[str, str] = {}
        self.direct_aliases: dict[str, str] = {}
        self.calls: Counter[str] = Counter()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name in {"httpx", "requests", "urllib.request"}:
                self.module_aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module == "urllib.request":
            for alias in node.names:
                if alias.name == "urlopen":
                    self.direct_aliases[alias.asname or alias.name] = "urlopen"
        elif module in {"httpx", "requests"}:
            allowed = _HTTPX if module == "httpx" else _REQUESTS
            for alias in node.names:
                if alias.name in allowed:
                    self.direct_aliases[alias.asname or alias.name] = f"{module}.{alias.name}"
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        callee = self._callee(node.func)
        if callee is not None:
            self.calls[callee] += 1
        self.generic_visit(node)

    def _callee(self, func: ast.expr) -> str | None:
        if isinstance(func, ast.Name):
            return self.direct_aliases.get(func.id)
        if not isinstance(func, ast.Attribute):
            return None
        if (
            func.attr == "urlopen"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "request"
            and isinstance(func.value.value, ast.Name)
            and self.module_aliases.get(func.value.value.id) == "urllib.request"
        ):
            return "urllib.request.urlopen"
        if not isinstance(func.value, ast.Name):
            return None
        module = self.module_aliases.get(func.value.id)
        if module == "httpx" and func.attr in _HTTPX:
            return f"httpx.{func.attr}"
        if module == "requests" and func.attr in _REQUESTS:
            return f"requests.{func.attr}"
        if module == "urllib.request" and func.attr == "urlopen":
            return "urllib.request.urlopen"
        return None


def scan_file(path: Path) -> Counter[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    scanner = _CallScanner()
    scanner.visit(tree)
    return scanner.calls


def scan_tree(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.py")):
        calls = scan_file(path)
        for callee, count in sorted(calls.items()):
            rows.append({
                "path": _display_path(path),
                "callee": callee,
                "count": count,
            })
    return rows


def _key(row: dict[str, object]) -> tuple[str, str]:
    return str(row["path"]), str(row["callee"])


def compare_inventory(
    actual: Iterable[dict[str, object]], expected: Iterable[dict[str, object]]
) -> list[str]:
    actual_map = {_key(row): int(row["count"]) for row in actual}
    expected_map = {_key(row): int(row["count"]) for row in expected}
    deltas: list[str] = []
    for key in sorted(actual_map.keys() | expected_map.keys()):
        current = actual_map.get(key)
        wanted = expected_map.get(key)
        path, callee = key
        if wanted is None:
            deltas.append(f"+ {path} {callee} x{current}")
        elif current is None:
            deltas.append(f"- {path} {callee} expected={wanted} actual=0")
        elif current != wanted:
            deltas.append(f"~ {path} {callee} expected={wanted} actual={current}")
    return deltas


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    inventory_path = repo / "docs/security/legacy-outbound-http.json"
    root = repo / "apps/api/core"
    expected = json.loads(inventory_path.read_text())
    actual = scan_tree(root)
    deltas = compare_inventory(actual, expected)
    if deltas:
        print("Outbound HTTP bypass inventory mismatch:")
        for delta in deltas:
            print(delta)
        return 1
    print(f"Outbound HTTP bypass inventory OK: {len(actual)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
