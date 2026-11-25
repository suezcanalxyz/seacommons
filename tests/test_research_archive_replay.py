"""Archive replay accounting and resume tests (synthetic only)."""
import importlib.util
import sys
from pathlib import Path
import hashlib
import json

import pytest

scripts = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, scripts / (name + ".py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load("research_archive_sample_verify")
mod = load("research_archive_replay")


def fixture():
    prefix = "ais-history/oracle-export/20261026T185713Z"
    parts = [{"key": prefix + "/" + str(i), "rows": 2, "bytes": 1,
              "sha256": hashlib.sha256(bytes([i])).hexdigest()} for i in range(3)]
    manifest = {"prefix": prefix, "complete": True, "format": "parquet",
                "tables": {"vessel_tracks": {"complete": True, "rows": 6, "parts": parts}}}
    def get(key, limit):
        return json.dumps(manifest).encode() if key.endswith("manifest.json") else bytes([int(key[-1])])
    return manifest, get


def test_resume_and_accounting(monkeypatch):
    manifest, get = fixture()
    state = mod.new_checkpoint(manifest)
    reads = []
    def inspect(part, data, name):
        reads.append(part["key"])
        return {"rows": 2, "bytes": 1, "quality": {"coordinate_in_range_nonzero": 2},
                "schema": "synthetic"}
    monkeypatch.setattr(mod, "inspect_part", inspect)
    def batch():
        return mod.run_batch(manifest, get, state, lambda s: None, table_name="vessel_tracks",
                             max_parts=2, max_bytes=10, max_seconds=10)
    assert batch()["batch_parts"] == 2
    assert batch()["batch_parts"] == 1
    assert batch()["batch_parts"] == 0
    assert len(set(reads)) == len(reads) == 3
    assert state["tables"]["vessel_tracks"]["rows"] == 6


def test_failure_does_not_advance(monkeypatch):
    manifest, get = fixture()
    state = mod.new_checkpoint(manifest)
    def inspect(part, data, name):
        raise ValueError("bad part")
    monkeypatch.setattr(mod, "inspect_part", inspect)
    with pytest.raises(ValueError, match="bad part"):
        mod.run_batch(manifest, get, state, lambda s: pytest.fail("unexpected save"),
                      table_name="vessel_tracks", max_parts=2, max_bytes=10, max_seconds=10)
    assert state["tables"]["vessel_tracks"]["next_part"] == 0


def test_checkpoint_mismatch_rejected():
    manifest, _ = fixture()
    state = mod.new_checkpoint(manifest)
    state["tables"]["vessel_tracks"]["rows"] = 1
    with pytest.raises(ValueError, match="row mismatch"):
        mod.validate_checkpoint(state, manifest)


def test_actual_parquet_quality():
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    table = pa.table({"lat": [35., None, 91., 0., float("nan"), None],
                      "lon": [15., 1., 2., 0., 1., 181.],
                      "observed_at": ["2026-01-01T01:00:00Z", None, "2026-01-01",
                                      "2026-01-01T01:00:00+01:00", None, None]})
    buf = pa.BufferOutputStream()
    pq.write_table(table, buf)
    data = buf.getvalue().to_pybytes()
    part = {"bytes": len(data), "rows": 6, "sha256": hashlib.sha256(data).hexdigest()}
    result = mod.inspect_part(part, data, "source_observations")
    assert result["quality"] == {
        "coordinate_missing": 2, "coordinate_out_of_range_or_nonfinite": 2,
        "coordinate_zero_zero_review": 1, "coordinate_in_range_nonzero": 1,
        "timestamp_missing": 3, "timestamp_explicit_offset_suffix": 2,
        "timestamp_without_offset_suffix": 1,
    }
    with pytest.raises(ValueError, match="integrity"):
        mod.inspect_part(part, data + b"x", "source_observations")
