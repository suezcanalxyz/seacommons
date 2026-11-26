"""Regression tests for descriptive archive profile, with synthetic records only."""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load("research_archive_sample_verify")
load("research_archive_replay")
mod = load("research_archive_profile")


def test_speed_boundaries():
    values = [None, -1, float("nan"), float("inf"), False, 0, .5, 1, 5, 15, 30, 60]
    assert [mod.reported_speed_class(v) for v in values] == [
        "missing", "invalid", "invalid", "invalid", "invalid", "zero_or_imputed_missing",
        "0_to_1", "1_to_5", "5_to_15", "15_to_30", "30_to_60", "60_or_more_review",
    ]


def test_time_basis_and_utc_month_boundary():
    assert mod.time_class(None) == ("missing", None)
    assert mod.time_class("not-a-date") == ("unparseable", None)
    assert mod.time_class(datetime(2026, 1, 1)) == ("naive", "2026-01")
    assert mod.time_class("2026-01-01T00:10:00+01:00") == ("explicit_offset", "2025-12")
    assert mod.time_class(datetime(2026, 1, 1, tzinfo=timezone.utc)) == ("explicit_offset", "2026-01")


def test_profile_accounting_no_identifiers():
    pa = pytest.importorskip("pyarrow")
    table = pa.table({"mmsi": ["synthetic-secret", "another-secret"],
                      "ts": [datetime(2026, 1, 1), datetime(2026, 2, 1)], "sog": [0., 12.]})
    result = mod.profile_table(table, "vessel_tracks")
    assert result["rows"] == 2
    assert result["time_quality"] == {"naive": 2}
    assert result["calendar_months"] == {"naive:2026-01": 1, "naive:2026-02": 1}
    assert result["reported_sog_knots"] == {"zero_or_imputed_missing": 1, "5_to_15": 1}
    assert "secret" not in str(result)


def test_zero_provenance_and_missing():
    assert mod.reported_speed_class(None) == "missing"
    assert mod.reported_speed_class(0) == "zero_or_imputed_missing"
    assert mod.reported_speed_class(0, zero_verified=True) == "zero"
    assert mod.reported_speed_class(None, zero_verified=True) == "missing"


def test_offset_equivalence_and_naive_separation():
    assert mod.time_class("2026-10-01T00:30:00+02:00") == mod.time_class("2026-09-30T22:30:00Z")
    assert mod.time_class("2026-10-01T00:30:00") == ("naive", "2026-10")


def test_verified_parquet_sample_produces_validated_aggregates():
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    prefix = "ais-history/oracle-export/20261026T185713Z"
    manifest = {"prefix": prefix, "complete": True, "format": "parquet", "tables": {}}
    objects = {}
    for name, columns in {
        "vessel_tracks": {"ts": ["2026-01-01", None], "sog": [0.0, None]},
        "source_observations": {"observed_at": ["2026-01-01T00:00:00+01:00", "invalid"]},
    }.items():
        sink = pa.BufferOutputStream()
        pq.write_table(pa.table(columns), sink)
        data = sink.getvalue().to_pybytes()
        parts = []
        for index in range(3):
            key = f"{prefix}/{name}-{index}.parquet"
            objects[key] = data
            parts.append({"key": key, "rows": 2, "bytes": len(data),
                          "sha256": hashlib.sha256(data).hexdigest()})
        manifest["tables"][name] = {"complete": True, "rows": 6, "parts": parts}
    objects[f"{prefix}/manifest.json"] = json.dumps(manifest).encode()
    reads = []

    def get(key, limit):
        reads.append(key)
        return objects[key]

    snapshot = mod.profile_archive(manifest, get, 2)
    assert snapshot["manifest_sha256"] == mod.manifest_digest(manifest)
    assert snapshot["status"] == "incomplete"
    assert len(reads) == 5 and not any("-1.parquet" in key for key in reads)
    tracks = snapshot["tables"]["vessel_tracks"]
    assert (tracks["sample_rows"], tracks["total_rows"]) == (4, 6)
    assert tracks["reported_sog_knots"] == {"zero_or_imputed_missing": 2, "missing": 2}
    observations = snapshot["tables"]["source_observations"]
    assert observations["calendar_months"] == {"explicit_offset:2025-12": 2}
    assert observations["time_quality"] == {"explicit_offset": 2, "unparseable": 2}
    objects[reads[1]] += b"tampered"
    with pytest.raises(ValueError, match="integrity"):
        mod.profile_archive(manifest, get, 2)
