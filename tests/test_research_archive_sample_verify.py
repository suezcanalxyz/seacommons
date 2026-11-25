"""Safety tests for the read-only research archive sample."""
import importlib.util
from pathlib import Path
import hashlib
import json

import pytest

spec = importlib.util.spec_from_file_location(
    "research_archive_sample_verify",
    Path(__file__).resolve().parents[1] / "scripts/research_archive_sample_verify.py",
)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def manifest():
    prefix = "ais-history/oracle-export/20261026T185713Z"
    return {
        "prefix": prefix, "complete": True, "format": "parquet",
        "tables": {"vessel_tracks": {"complete": True, "rows": 2, "parts": [
            {"key": prefix + "/part-1", "rows": 1, "bytes": 1, "sha256": hashlib.sha256(b"a").hexdigest()},
            {"key": prefix + "/part-2", "rows": 1, "bytes": 1, "sha256": hashlib.sha256(b"b").hexdigest()},
        ]}},
    }


def test_sample_indices():
    assert mod.sample_indices(3853, 3) == [0, 1926, 3852]
    assert mod.sample_indices(2, 10) == [0, 1]
    assert mod.sample_indices(1, 3) == [0]
    with pytest.raises(ValueError):
        mod.sample_indices(0, 3)


def test_manifest_accounting_and_scope():
    data = manifest()
    mod.validate_manifest(data)
    data["tables"]["vessel_tracks"]["rows"] = 3
    with pytest.raises(ValueError, match="row count"):
        mod.validate_manifest(data)
    data = manifest()
    data["tables"]["vessel_tracks"]["parts"][1]["key"] = "outside"
    with pytest.raises(ValueError, match="out-of-scope"):
        mod.validate_manifest(data)


def test_duplicate_object_rejected():
    data = manifest()
    parts = data["tables"]["vessel_tracks"]["parts"]
    parts[1]["key"] = parts[0]["key"]
    with pytest.raises(ValueError, match="duplicate"):
        mod.validate_manifest(data)


def test_remote_manifest_mismatch_stops_before_part_read():
    data = manifest()
    reads = []
    def get(key, limit):
        reads.append(key)
        return json.dumps({}).encode()
    with pytest.raises(ValueError, match="manifest mismatch"):
        mod.verify_sample(data, get, 3)
    assert reads == [data["prefix"] + "/manifest.json"]


def test_sample_aggregate_only(monkeypatch):
    data = manifest()
    def get(key, limit):
        if key.endswith("manifest.json"):
            return json.dumps(data).encode()
        return b"a" if key.endswith("part-1") else b"b"
    monkeypatch.setattr(mod, "verify_part", lambda part, payload: (part["rows"], "schema"))
    result = mod.verify_sample(data, get, 3)
    assert result["tables"]["vessel_tracks"]["verified_parts"] == 2
    assert result["tables"]["vessel_tracks"]["decoded_rows"] == 2
    assert "part-1" not in json.dumps(result)
