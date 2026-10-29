# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lossless, immutable AIS track archives (Parquet+Zstandard), without deletes.

Pack, verify and read back one bounded UTC-day batch. Callers must opt into
publishing to an explicitly configured private object store. This module
does NOT connect to PostgreSQL, prune hot rows, or manage retention policy.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core import object_store
from core.config import config

SCHEMA_VERSION = "vessel_tracks_parquet_v2"
MAX_ROWS_PER_SEGMENT = 2000
FIELDS = (
    "id", "mmsi", "ts", "received_at", "lat", "lon",
    "sog", "cog", "heading", "nav_status", "source",
)


def _pyarrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "AIS Parquet archiving requires the optional pyarrow archive dependency"
        ) from exc
    return pa, pq


def _datetime(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("AIS archive timestamp must be ISO-8601/datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _row(raw: dict[str, Any]) -> dict[str, Any]:
    if set(raw) != set(FIELDS):
        missing = set(FIELDS) - set(raw)
        extra = set(raw) - set(FIELDS)
        raise ValueError(f"AIS archive schema mismatch: missing={missing}, extra={extra}")
    row = dict(raw)
    row["id"] = int(row["id"])
    row["mmsi"] = str(row["mmsi"])
    row["source"] = str(row["source"])
    row["ts"] = _datetime(row["ts"])
    row["received_at"] = _datetime(row["received_at"])
    row["lat"] = float(row["lat"])
    row["lon"] = float(row["lon"])
    for field in ("sog", "cog", "heading"):
        row[field] = float(row[field]) if row[field] is not None else None
    row["nav_status"] = int(row["nav_status"]) if row["nav_status"] is not None else None
    if (
        row["id"] < 0
        or not row["mmsi"]
        or not row["source"]
        or not -90 <= row["lat"] <= 90
        or not -180 <= row["lon"] <= 180
        or any(
            not math.isfinite(row[key])
            for key in ("lat", "lon", "sog", "cog", "heading")
            if row[key] is not None
        )
    ):
        raise ValueError("AIS archive contains invalid observation")
    return row


def _canonical(raw_rows: list[dict[str, Any]]) -> bytes:
    return json.dumps(
        [{k: (v.isoformat() if isinstance(v, datetime) else v)
          for k, v in row.items()} for row in raw_rows],
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _schema(pa: Any):
    return pa.schema(
        [
            pa.field("id", pa.int64(), nullable=False),
            pa.field("mmsi", pa.string(), nullable=False),
            pa.field("ts", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("received_at", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("lat", pa.float64(), nullable=False),
            pa.field("lon", pa.float64(), nullable=False),
            pa.field("sog", pa.float64()),
            pa.field("cog", pa.float64()),
            pa.field("heading", pa.float64()),
            pa.field("nav_status", pa.int32()),
            pa.field("source", pa.string(), nullable=False),
        ],
        metadata={b"seacommons_schema": SCHEMA_VERSION.encode("ascii")},
    )


@dataclass(frozen=True)
class ArchivePackage:
    object_key: str
    manifest_key: str
    parquet_bytes: bytes
    manifest_bytes: bytes
    row_count: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.parquet_bytes).hexdigest()


def _decode(parquet_bytes: bytes) -> list[dict[str, Any]]:
    pa, pq = _pyarrow()
    table = pq.read_table(io.BytesIO(parquet_bytes))
    if table.schema.metadata is None or table.schema.metadata.get(
        b"seacommons_schema"
    ) != SCHEMA_VERSION.encode("ascii"):
        raise ValueError("AIS archive schema version mismatch")
    return [_row(row) for row in table.to_pylist()]


def build_archive(rows: list[dict[str, Any]]) -> ArchivePackage:
    """Build one lossless UTC-day segment in memory; zero storage writes."""
    if not 1 <= len(rows) <= MAX_ROWS_PER_SEGMENT:
        raise ValueError("AIS archive segment size must be 1..2000 rows")
    clean = [_row(row) for row in rows]
    if len({row["id"] for row in clean}) != len(clean):
        raise ValueError("duplicate AIS row ID in archive segment")
    utc_days = {row["ts"].date() for row in clean}
    if len(utc_days) != 1:
        raise ValueError("AIS archive segment must contain one UTC day")
    clean.sort(key=lambda r: r["id"])
    pa, pq = _pyarrow()
    table = pa.Table.from_pylist(clean, schema=_schema(pa))
    buffer = io.BytesIO()
    pq.write_table(
        table, buffer, compression="zstd", compression_level=5,
        row_group_size=1000, use_dictionary=True, write_statistics=True,
    )
    parquet_bytes = buffer.getvalue()
    decoded = _decode(parquet_bytes)
    if decoded != clean:
        raise ValueError("AIS Parquet roundtrip differs from input")
    digest = hashlib.sha256(parquet_bytes).hexdigest()
    day = next(iter(utc_days))
    key = (
        f"cold/ais-tracks/v2/{day:%Y/%m/%d}/"
        f"{clean[0]['id']}-{clean[-1]['id']}-{digest[:24]}.parquet"
    )
    manifest = {
        "schema": SCHEMA_VERSION,
        "format": "parquet",
        "compression": "zstd",
        "object_key": key,
        "row_count": len(clean),
        "id_min": min(row["id"] for row in clean),
        "id_max": max(row["id"] for row in clean),
        "utc_day": day.isoformat(),
        "ts_min": min(row["ts"] for row in clean).isoformat(),
        "ts_max": max(row["ts"] for row in clean).isoformat(),
        "source_counts": dict(sorted(Counter(row["source"] for row in clean).items())),
        "parquet_bytes": len(parquet_bytes),
        "parquet_sha256": digest,
        "canonical_rows_sha256": hashlib.sha256(_canonical(clean)).hexdigest(),
    }
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return ArchivePackage(
        object_key=key, manifest_key=key + ".manifest.json",
        parquet_bytes=parquet_bytes, manifest_bytes=manifest_bytes,
        row_count=len(clean),
    )


def _validate_store_config() -> None:
    if not all((
        config.OBJECT_STORAGE_ENDPOINT,
        config.OBJECT_STORAGE_ACCESS_KEY,
        config.OBJECT_STORAGE_SECRET_KEY,
        config.OBJECT_STORAGE_BUCKET,
    )):
        raise RuntimeError("R2 credentials unavailable; refusing filesystem fallback")
    if not config.OBJECT_STORAGE_SECURE:
        raise RuntimeError("AIS cold archive requires an HTTPS object-store endpoint")


def publish_verified_archive(package: ArchivePackage) -> dict[str, Any]:
    """Upload and verify private objects; intentionally NEVER delete source data."""
    _validate_store_config()
    object_store.put(package.object_key, package.parquet_bytes, "application/vnd.apache.parquet")
    fetched = object_store.get(package.object_key)
    if hashlib.sha256(fetched).hexdigest() != package.sha256:
        raise ValueError("AIS Parquet upload/download SHA-256 mismatch")
    if len(_decode(fetched)) != package.row_count:
        raise ValueError("AIS Parquet restored row count mismatch")
    object_store.put(package.manifest_key, package.manifest_bytes, "application/json")
    if object_store.get(package.manifest_key) != package.manifest_bytes:
        raise ValueError("AIS archive manifest readback mismatch")
    return {
        "object_key": package.object_key,
        "manifest_key": package.manifest_key,
        "rows": package.row_count,
        "sha256": package.sha256,
        "verified": True,
        "postgres_rows_deleted": 0,
    }


def restore_verified_archive(manifest_key: str) -> list[dict[str, Any]]:
    """Read an archive only if manifest, digest, row count and rows all match."""
    _validate_store_config()
    if not manifest_key.startswith("cold/ais-tracks/v2/") or not manifest_key.endswith(
        ".parquet.manifest.json"
    ):
        raise ValueError("invalid AIS archive manifest path")
    manifest = json.loads(object_store.get(manifest_key))
    if (
        manifest.get("schema") != SCHEMA_VERSION
        or manifest.get("object_key") + ".manifest.json" != manifest_key
    ):
        raise ValueError("AIS archive manifest schema/key mismatch")
    blob = object_store.get(manifest["object_key"])
    if hashlib.sha256(blob).hexdigest() != manifest["parquet_sha256"]:
        raise ValueError("AIS archive checksum mismatch")
    if len(blob) != manifest["parquet_bytes"]:
        raise ValueError("AIS archive byte-length mismatch")
    rows = _decode(blob)
    if len(rows) != manifest["row_count"]:
        raise ValueError("AIS archive restored row count mismatch")
    if hashlib.sha256(_canonical(rows)).hexdigest() != manifest["canonical_rows_sha256"]:
        raise ValueError("AIS archive restored row-content mismatch")
    return rows
