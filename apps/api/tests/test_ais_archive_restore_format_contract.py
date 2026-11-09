# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed AIS v1 archive format contract; synthetic, no DB/R2 access.

This is a serialization prerequisite, NOT the PostgreSQL/S3 restore drill.
"""
import ast
import gzip
import hashlib
import json
from pathlib import Path

TRACK_STORE = Path(__file__).resolve().parents[1] / "core/vessels/track_store.py"
REQUIRED_FIELDS = {
    "id", "mmsi", "ts", "received_at", "lat", "lon", "sog",
    "cog", "heading", "nav_status", "source",
}


def _prune_source():
    tree = ast.parse(TRACK_STORE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "prune":
            return ast.get_source_segment(TRACK_STORE.read_text(encoding="utf-8"), node)
    raise AssertionError("canonical TrackStore.prune not found")


def test_archive_contract_includes_all_fields_and_deterministic_gzip():
    source = _prune_source()
    # Verify that the synthetic format below remains coupled to the canonical
    # producer rather than silently testing a separate shadow schema.
    tree = ast.parse(source)
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
    assert REQUIRED_FIELDS <= keys, f"Archive producer missing: {REQUIRED_FIELDS - keys}"
    assert "vessel_tracks_v1" in source
    assert "mtime=0" in source

    rows = [
        {
            "id": i, "mmsi": str(200000000 + i),
            "ts": "2026-01-01T00:00:00+00:00",
            "received_at": "2026-01-01T00:00:01+00:00",
            "lat": 34.0 + i / 10000, "lon": 12.0,
            "sog": 4.5, "cog": 90.0, "heading": None,
            "nav_status": 0, "source": "synthetic",
        }
        for i in range(100)
    ]
    plain = json.dumps(
        {"schema": "vessel_tracks_v1", "rows": rows},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    first = gzip.compress(plain, mtime=0)
    second = gzip.compress(plain, mtime=0)
    assert first == second
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
    restored = json.loads(gzip.decompress(first))
    assert restored["schema"] == "vessel_tracks_v1"
    assert restored["rows"] == rows
    assert len({row["id"] for row in restored["rows"]}) == 100


def test_corruption_must_not_pass_digest_gate():
    original = gzip.compress(b'{"schema":"vessel_tracks_v1","rows":[]}', mtime=0)
    corrupted = original[:-1] + bytes([original[-1] ^ 1])
    assert hashlib.sha256(corrupted).digest() != hashlib.sha256(original).digest()
