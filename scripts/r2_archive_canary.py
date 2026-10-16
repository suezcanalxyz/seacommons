# SPDX-License-Identifier: AGPL-3.0-or-later
"""Manual, non-destructive R2 archive canary.

Run with:
    PYTHONPATH=apps/api apps/api/.venv/bin/python scripts/r2_archive_canary.py
    PYTHONPATH=apps/api apps/api/.venv/bin/python scripts/r2_archive_canary.py --execute

Dry-run is the default. --execute must be issued explicitly in an authorized
service environment containing R2 credentials. This test NEVER prunes tracks,
touches database records, removes objects, or exports actual AIS observations.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import uuid
from datetime import datetime, timezone

from core import object_store
from core.config import config


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def run(*, execute: bool = False) -> dict:
    """Round-trip test one synthetic compressed archive plus its SHA-256 manifest."""
    if not execute:
        return {"status": "dry_run", "writes": 0, "deletes": 0}

    # Explicitly prohibit object_store's development-only local-file fallback.
    if not all(
        (
            config.OBJECT_STORAGE_ENDPOINT,
            config.OBJECT_STORAGE_ACCESS_KEY,
            config.OBJECT_STORAGE_SECRET_KEY,
            config.OBJECT_STORAGE_BUCKET,
        )
    ):
        raise RuntimeError("R2 not configured; refusing local fallback")

    timestamp = datetime.now(timezone.utc)
    canary_id = uuid.uuid4().hex
    key_base = (
        "healthchecks/ais-archive-canary/v1/"
        f"{timestamp:%Y/%m/%d}/{canary_id}"
    )
    key = key_base + ".json.gz"
    manifest_key = key_base + ".manifest.json"
    source = _json_bytes(
        {
            "schema": "seacommons_ais_archive_canary_v1",
            "canary_id": canary_id,
            "sample": [
                {"mmsi": "000000001", "ts": "2026-10-15T00:00:00+00:00",
                 "lat": 35.0, "lon": 14.0, "source": "synthetic"}
            ],
        }
    )
    compressed = gzip.compress(source, mtime=0)
    compressed_sha = hashlib.sha256(compressed).hexdigest()
    original_sha = hashlib.sha256(source).hexdigest()
    manifest = {
        "schema": "seacommons_ais_archive_manifest_v1",
        "canary": True,
        "object_key": key,
        "compressed_bytes": len(compressed),
        "compressed_sha256": compressed_sha,
        "uncompressed_sha256": original_sha,
        "rows": 1,
    }

    object_store.put(key, compressed, "application/gzip")
    fetched = object_store.get(key)
    if hashlib.sha256(fetched).hexdigest() != compressed_sha:
        raise ValueError("R2 compressed object SHA-256 mismatch")
    if hashlib.sha256(gzip.decompress(fetched)).hexdigest() != original_sha:
        raise ValueError("R2 decompressed data SHA-256 mismatch")

    manifest_bytes = _json_bytes(manifest)
    object_store.put(manifest_key, manifest_bytes, "application/json")
    if object_store.get(manifest_key) != manifest_bytes:
        raise ValueError("R2 manifest round-trip mismatch")

    return {
        "status": "verified",
        "writes": 2,
        "deletes": 0,
        "object_key": key,
        "manifest_key": manifest_key,
        "compressed_sha256": compressed_sha,
        "original_sha256": original_sha,
        "compressed_bytes": len(compressed),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true",
        help="Explicitly upload and restore synthetic canary objects on configured R2",
    )
    args = parser.parse_args()
    try:
        result = run(execute=args.execute)
    except Exception as exc:
        print(_json_bytes({"status": "failed", "reason": type(exc).__name__}).decode())
        return 1
    print(_json_bytes(result).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
