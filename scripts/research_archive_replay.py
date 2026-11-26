#!/usr/bin/env python3
"""Incremental archive verification and descriptive quality census, not case adjudication."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from research_archive_sample_verify import (
    MAX_MANIFEST_BYTES, MAX_PART_BYTES, make_reader, validate_manifest,
)

METHOD = "archive-quality/v1"
MAX_DECODED_BYTES = 128 * 1024 * 1024
MAX_ROWS_PER_PART = 10_000


def manifest_digest(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def decode_verified_part(part: dict[str, Any], data: bytes):
    """Verify and decode one bounded immutable archive object."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    if len(data) != part["bytes"] or hashlib.sha256(data).hexdigest() != part["sha256"]:
        raise ValueError("object integrity mismatch")
    file = pq.ParquetFile(pa.BufferReader(data))
    meta = file.metadata
    if meta.num_rows != part["rows"] or meta.num_rows > MAX_ROWS_PER_PART:
        raise ValueError("row budget or manifest mismatch")
    decoded_size = sum(
        meta.row_group(i).column(j).total_uncompressed_size
        for i in range(meta.num_row_groups) for j in range(meta.num_columns)
    )
    if not 0 <= decoded_size <= MAX_DECODED_BYTES:
        raise ValueError("decoded size budget exceeded")
    table = file.read(use_threads=False)
    if table.num_rows != part["rows"]:
        raise ValueError("decoded row mismatch")
    return table


def inspect_part(part: dict[str, Any], data: bytes, table_name: str) -> dict[str, Any]:
    """Verify the original bytes and compute aggregate quality without releasing records."""
    import pyarrow as pa
    import pyarrow.compute as pc

    table = decode_verified_part(part, data)
    if table_name not in {"vessel_tracks", "source_observations"}:
        raise ValueError("unsupported table")
    if not {"lat", "lon"} <= set(table.column_names):
        raise ValueError("missing coordinate fields")
    lat, lon = table["lat"], table["lon"]
    if not all(pa.types.is_floating(x.type) or pa.types.is_integer(x.type)
               or pa.types.is_null(x.type) for x in (lat, lon)):
        raise ValueError("unexpected coordinate type")
    lat, lon = pc.cast(lat, pa.float64()), pc.cast(lon, pa.float64())

    def count(mask) -> int:
        return int(pc.sum(pc.cast(pc.fill_null(mask, False), pa.int64())).as_py() or 0)

    missing = pc.or_(pc.is_null(lat), pc.is_null(lon))
    in_range = pc.and_kleene(pc.and_kleene(pc.is_finite(lat), pc.is_finite(lon)),
        pc.and_kleene(pc.less_equal(pc.abs(lat), 90), pc.less_equal(pc.abs(lon), 180)))
    zero = pc.and_kleene(pc.equal(lat, 0), pc.equal(lon, 0))
    n_missing, n_valid, n_zero = count(missing), count(in_range), count(zero)
    quality = {
        "coordinate_missing": n_missing,
        "coordinate_out_of_range_or_nonfinite": table.num_rows - n_missing - n_valid,
        "coordinate_zero_zero_review": n_zero,
        "coordinate_in_range_nonzero": n_valid - n_zero,
    }
    timestamp = "ts" if table_name == "vessel_tracks" else "observed_at"
    if timestamp not in table.column_names:
        raise ValueError("missing timestamp field")
    col = table[timestamp]
    quality["timestamp_missing"] = col.null_count
    if pa.types.is_timestamp(col.type):
        quality["timestamp_timezone_naive"] = len(col) - col.null_count if col.type.tz is None else 0
    elif pa.types.is_string(col.type) or pa.types.is_large_string(col.type):
        explicit = pc.match_substring_regex(col, r"(Z|[+-][0-9]{2}:?[0-9]{2})$")
        quality["timestamp_explicit_offset_suffix"] = count(explicit)
        quality["timestamp_without_offset_suffix"] = len(col) - col.null_count - count(explicit)
    elif not pa.types.is_null(col.type):
        raise ValueError("unexpected timestamp type")
    return {"rows": table.num_rows, "bytes": len(data), "quality": quality,
            "schema": hashlib.sha256(str(table.schema).encode()).hexdigest()}


def new_checkpoint(manifest: dict[str, Any]) -> dict[str, Any]:
    return {"method": METHOD, "manifest_sha256": manifest_digest(manifest),
            "tables": {name: {"next_part": 0, "rows": 0, "bytes": 0, "quality": {},
                              "schemas": {}} for name in manifest["tables"]}}


def validate_checkpoint(state: dict[str, Any], manifest: dict[str, Any]) -> None:
    if state["method"] != METHOD or state["manifest_sha256"] != manifest_digest(manifest):
        raise ValueError("checkpoint method or manifest mismatch")
    if set(state["tables"]) != set(manifest["tables"]):
        raise ValueError("checkpoint table mismatch")
    for name, row in state["tables"].items():
        parts = manifest["tables"][name]["parts"]
        cursor = row["next_part"]
        if type(cursor) is not int or not 0 <= cursor <= len(parts):
            raise ValueError("invalid checkpoint cursor")
        if row["rows"] != sum(p["rows"] for p in parts[:cursor]):
            raise ValueError("checkpoint row mismatch")
        if row["bytes"] != sum(p["bytes"] for p in parts[:cursor]):
            raise ValueError("checkpoint byte mismatch")
        if sum(row["schemas"].values()) != cursor:
            raise ValueError("checkpoint schema count mismatch")
        if sum(v for k, v in row["quality"].items() if k.startswith("coordinate_")) != row["rows"]:
            raise ValueError("checkpoint coordinate accounting mismatch")


def atomic_save(path: Path, state: dict[str, Any]) -> None:
    """Persist only cumulative aggregate counters; replace atomically after success."""
    fd, temporary = tempfile.mkstemp(prefix=".archive-checkpoint-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run_batch(manifest, get, state, save, *, table_name, max_parts, max_bytes, max_seconds):
    validate_manifest(manifest)
    validate_checkpoint(state, manifest)
    if json.loads(get(manifest["prefix"] + "/manifest.json", MAX_MANIFEST_BYTES)) != manifest:
        raise ValueError("remote manifest differs")
    parts = manifest["tables"][table_name]["parts"]
    row = state["tables"][table_name]
    count, transferred = 0, 0
    started = time.monotonic()
    while row["next_part"] < len(parts) and count < max_parts:
        if time.monotonic() - started >= max_seconds:
            break
        part = parts[row["next_part"]]
        if part["bytes"] > MAX_PART_BYTES:
            raise ValueError("part exceeds object budget")
        if transferred + part["bytes"] > max_bytes:
            break
        report = inspect_part(part, get(part["key"], MAX_PART_BYTES), table_name)
        row["next_part"] += 1
        row["rows"] += report["rows"]
        row["bytes"] += report["bytes"]
        row["quality"] = dict(Counter(row["quality"]) + Counter(report["quality"]))
        schemas = Counter(row["schemas"])
        schemas[report["schema"]] += 1
        row["schemas"] = dict(schemas)
        validate_checkpoint(state, manifest)
        save(state)
        transferred += report["bytes"]
        count += 1
    return {"method": METHOD, "table": table_name, "batch_parts": count,
            "batch_bytes": transferred, "batch_seconds": round(time.monotonic()-started, 3),
            "scope": "verified/decode quality accounting; not full database restoration or investigation",
            "tables": {name: {"verified_parts": r["next_part"],
                              "total_parts": len(manifest["tables"][name]["parts"]),
                              "verified_rows": r["rows"], "total_rows": manifest["tables"][name]["rows"],
                              "quality": r["quality"], "schema_variants": len(r["schemas"])}
                       for name, r in state["tables"].items()}}


def main() -> None:
    import fcntl

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path.home()/".config/seacommons/r2.env")
    parser.add_argument("--table", choices=["vessel_tracks", "source_observations"], required=True)
    parser.add_argument("--max-parts", type=int, default=12)
    parser.add_argument("--max-bytes", type=int, default=24 * 1024 * 1024)
    parser.add_argument("--max-seconds", type=int, default=20)
    args = parser.parse_args()
    if not (1 <= args.max_parts <= 64 and MAX_PART_BYTES <= args.max_bytes <= 64*1024*1024
            and 1 <= args.max_seconds <= 45):
        parser.error("invalid resource budget")
    try:
        if args.manifest.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("manifest size budget")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validate_manifest(manifest)
        args.checkpoint.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with args.checkpoint.with_suffix(".lock").open("a", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = (json.loads(args.checkpoint.read_text(encoding="utf-8"))
                     if args.checkpoint.exists() else new_checkpoint(manifest))
            result = run_batch(manifest, make_reader(args.config), state,
                               lambda s: atomic_save(args.checkpoint, s),
                               table_name=args.table, max_parts=args.max_parts,
                               max_bytes=args.max_bytes, max_seconds=args.max_seconds)
            print(json.dumps(result, sort_keys=True, indent=2))
    except Exception as exc:
        parser.exit(1, f"Archive batch stopped ({type(exc).__name__}); prior verified checkpoints retained.\n")


if __name__ == "__main__":
    main()
