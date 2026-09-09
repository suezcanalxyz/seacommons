# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from scripts.check_outbound_http_bypasses import compare_inventory, scan_tree


def _write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)


def test_inventoried_direct_call_passes(tmp_path: Path) -> None:
    _write(tmp_path, "apps/api/core/legacy.py", "import httpx\nhttpx.get('https://example.com')\n")
    actual = scan_tree(tmp_path / "apps/api/core")
    expected = [{"path": "apps/api/core/legacy.py", "callee": "httpx.get", "count": 1}]
    assert compare_inventory(actual, expected) == []

def test_new_direct_call_fails_inventory(tmp_path: Path) -> None:
    _write(tmp_path, "apps/api/core/new.py", "import requests\nrequests.post('https://example.com')\n")
    actual = scan_tree(tmp_path / "apps/api/core")
    deltas = compare_inventory(actual, [])
    assert deltas == ["+ apps/api/core/new.py requests.post x1"]


def test_extra_existing_call_fails_by_count(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/api/core/legacy.py",
        "import httpx\nhttpx.get('https://a')\nhttpx.get('https://b')\n",
    )
    actual = scan_tree(tmp_path / "apps/api/core")
    expected = [{"path": "apps/api/core/legacy.py", "callee": "httpx.get", "count": 1}]
    assert compare_inventory(actual, expected) == [
        "~ apps/api/core/legacy.py httpx.get expected=1 actual=2"
    ]

def test_imported_urlopen_and_requests_session_are_detected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/api/core/mixed.py",
        "from urllib.request import urlopen\nimport requests\nurlopen('https://a')\nrequests.Session()\n",
    )
    actual = scan_tree(tmp_path / "apps/api/core")
    assert actual == [
        {"path": "apps/api/core/mixed.py", "callee": "requests.Session", "count": 1},
        {"path": "apps/api/core/mixed.py", "callee": "urlopen", "count": 1},
    ]


def test_canonical_net_module_is_not_falsely_classified(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/api/core/net/outbound.py",
        "from core.net.transport import send_pinned\ndef fetch():\n    return send_pinned\n",
    )
    assert scan_tree(tmp_path / "apps/api/core") == []

def test_import_urllib_request_module_call_is_detected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/api/core/urllib_style.py",
        "import urllib.request\nurllib.request.urlopen('https://example.com')\n",
    )
    assert scan_tree(tmp_path / "apps/api/core") == [
        {
            "path": "apps/api/core/urllib_style.py",
            "callee": "urllib.request.urlopen",
            "count": 1,
        }
    ]
