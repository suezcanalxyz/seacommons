# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only verification of PostgreSQL dump objects referenced by an R2 manifest.

Run on a separate verification machine, not on a CPU-constrained database VM.
Metadata mode checks object presence/size only; --deep streams every object and
checks SHA-256 without writing dump files. Neither mode proves pg_restore works.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def validate_manifest(items: object, *, prefix: str = "postgresql-backups/") -> list[dict]:
    if not isinstance(items, list) or not items:
        raise ValueError("manifest must be a non-empty JSON array")
    seen: set[str] = set()
    validated: list[dict] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"entry {index}: expected object")
        key, size, digest = item.get("key"), item.get("bytes"), item.get("sha256")
        if (not isinstance(key, str) or not key.startswith(prefix) or
                key.endswith("/") or ".." in key.split("/") or "\\" in key):
            raise ValueError(f"entry {index}: invalid backup object key")
        if key in seen:
            raise ValueError(f"entry {index}: duplicate backup object key")
        if type(size) is not int or size <= 0:
            raise ValueError(f"entry {index}: invalid size")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError(f"entry {index}: invalid SHA-256")
        seen.add(key)
        validated.append({"key": key, "bytes": size, "sha256": digest})
    return validated


def verify_objects(
    entries: list[dict],
    *,
    stat: Callable[[str], object],
    stream: Callable[[str], object] | None = None,
) -> list[dict]:
    """Never trust a manifest's own `verified` flag as independent proof."""
    results = []
    for item in entries:
        key = item["key"]
        try:
            metadata = stat(key)
            actual_size = int(metadata.size)
            if actual_size != item["bytes"]:
                raise ValueError(f"size mismatch: {actual_size} != {item['bytes']}")
            status = "metadata_verified"
            if stream is not None:
                response = stream(key)
                digest = hashlib.sha256()
                count = 0
                try:
                    for chunk in response.stream(amt=1024 * 1024):
                        digest.update(chunk)
                        count += len(chunk)
                finally:
                    response.close()
                    response.release_conn()
                if count != item["bytes"]:
                    raise ValueError(f"stream size mismatch: {count} != {item['bytes']}")
                if digest.hexdigest() != item["sha256"]:
                    raise ValueError("SHA-256 mismatch")
                status = "sha256_verified"
            results.append({"key": key, "status": status, "bytes": actual_size})
        except Exception as exc:  # Report all failures; never alter the source objects.
            results.append({"key": key, "status": "failed", "error": str(exc)})
    return results


def _client(endpoint: str, access_key: str, secret_key: str):
    from minio import Minio  # Optional at import time, installed in SeaCommons API env.

    parsed = urlsplit(endpoint if "://" in endpoint else f"https://{endpoint}")
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
        raise ValueError("R2 endpoint must be an HTTPS hostname with no path")
    return Minio(parsed.netloc, access_key=access_key, secret_key=secret_key, secure=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--endpoint", default=os.getenv("R2_ENDPOINT", ""))
    parser.add_argument("--deep", action="store_true", help="Stream and SHA-256 every dump")
    args = parser.parse_args(argv)
    try:
        entries = validate_manifest(json.loads(args.manifest.read_text(encoding="utf-8")))
        access = os.getenv("R2_ACCESS_KEY_ID", "")
        secret = os.getenv("R2_SECRET_ACCESS_KEY", "")
        if not args.endpoint or not access or not secret:
            raise ValueError("R2_ENDPOINT, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY are required")
        client = _client(args.endpoint, access, secret)
        results = verify_objects(
            entries,
            stat=lambda key: client.stat_object(args.bucket, key),
            stream=(lambda key: client.get_object(args.bucket, key)) if args.deep else None,
        )
        print(json.dumps({"mode": "sha256" if args.deep else "metadata_only",
                          "objects": results, "passed": sum(x["status"] != "failed" for x in results),
                          "failed": sum(x["status"] == "failed" for x in results)}, indent=2))
        return 1 if any(x["status"] == "failed" for x in results) else 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"verification aborted: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
