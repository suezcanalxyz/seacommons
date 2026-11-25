#!/usr/bin/env python3
"""Read-only sampled AIS Parquet archive verification. Never prints keys or rows."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

MAX_MANIFEST_BYTES = 2_000_000
MAX_PART_BYTES = 8_000_000


def sample_indices(size: int, samples: int) -> list[int]:
    if size < 1 or samples < 1:
        raise ValueError("invalid sample budget")
    count = min(size, samples)
    return [0] if count == 1 else [i * (size - 1) // (count - 1) for i in range(count)]


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("complete") is not True or manifest.get("format") != "parquet":
        raise ValueError("incomplete or unsupported manifest")
    prefix = manifest["prefix"]
    if not re.fullmatch(r"ais-history/oracle-export/\d{8}T\d{6}Z", prefix):
        raise ValueError("unexpected archive prefix")
    tables = manifest["tables"]
    if not tables:
        raise ValueError("missing tables")
    keys = set()
    for table in tables.values():
        parts = table["parts"]
        if table.get("complete") is not True or not parts:
            raise ValueError("incomplete table")
        if sum(p["rows"] for p in parts) != table["rows"]:
            raise ValueError("row count mismatch")
        for part in parts:
            key = part["key"]
            if not key.startswith(prefix + "/") or key in keys:
                raise ValueError("duplicate or out-of-scope object")
            if not re.fullmatch(r"[a-f0-9]{64}", part["sha256"]):
                raise ValueError("invalid checksum")
            if type(part["rows"]) is not int or part["rows"] <= 0:
                raise ValueError("invalid row count")
            if type(part["bytes"]) is not int or part["bytes"] <= 0:
                raise ValueError("invalid size")
            keys.add(key)


def verify_part(part: dict[str, Any], data: bytes) -> tuple[int, str]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    if len(data) != part["bytes"] or hashlib.sha256(data).hexdigest() != part["sha256"]:
        raise ValueError("part checksum/length mismatch")
    table = pq.read_table(pa.BufferReader(data))
    if table.num_rows != part["rows"]:
        raise ValueError("part row count mismatch")
    return table.num_rows, hashlib.sha256(str(table.schema).encode()).hexdigest()


def verify_sample(manifest: dict[str, Any], get, samples: int) -> dict[str, Any]:
    validate_manifest(manifest)
    remote = json.loads(get(manifest["prefix"] + "/manifest.json", MAX_MANIFEST_BYTES))
    if remote != manifest:
        raise ValueError("remote/local manifest mismatch")
    report = {}
    for name, table in manifest["tables"].items():
        parts = table["parts"]
        verified_rows = 0
        schemas = set()
        indices = sample_indices(len(parts), samples)
        for index in indices:
            part = parts[index]
            if part["bytes"] > MAX_PART_BYTES:
                raise ValueError("part exceeds sample size budget")
            rows, schema = verify_part(part, get(part["key"], MAX_PART_BYTES))
            verified_rows += rows
            schemas.add(schema)
        report[name] = {
            "manifest_rows": table["rows"], "manifest_parts": len(parts),
            "verified_parts": len(indices), "decoded_rows": verified_rows,
            "schema_variants": len(schemas),
        }
    return {"scope": "sampled object readback; not full restore or historical analysis",
            "manifest_matches": True, "tables": report}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path.home() / ".config/seacommons/r2.env")
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.samples <= 10:
        parser.error("sample budget must be 1–10 per table")
    try:
        import boto3
        from botocore.config import Config

        if args.manifest.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("manifest exceeds size budget")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        cfg = {}
        for line in args.config.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                cfg[key.strip()] = value.strip().strip('"').strip("'")
        client = boto3.client(
            "s3", endpoint_url="https://" + cfg["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
            aws_access_key_id=cfg["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=cfg["R2_SECRET_ACCESS_KEY"], region_name="auto",
            config=Config(connect_timeout=5, read_timeout=8, retries={"total_max_attempts": 1}),
        )

        def get(key: str, limit: int) -> bytes:
            obj = client.get_object(Bucket=cfg["R2_BUCKET"], Key=key)
            try:
                if obj["ContentLength"] > limit:
                    raise ValueError("object exceeds size budget")
                data = obj["Body"].read(limit + 1)
                if len(data) != obj["ContentLength"]:
                    raise ValueError("object length mismatch")
                return data
            finally:
                obj["Body"].close()

        print(json.dumps(verify_sample(manifest, get, args.samples), indent=2, sort_keys=True))
    except Exception as exc:
        # SDK exceptions can contain credentials or sensitive object URLs.
        parser.exit(1, f"Archive verification failed ({type(exc).__name__}); no partial result emitted.\n")


if __name__ == "__main__":
    main()
