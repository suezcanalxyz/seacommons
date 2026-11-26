"""Canonical contract for bounded historical archive message aggregates."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any

METHOD = "historical-observation-profile/v2"
MAX_SAMPLE_BYTES = 64 * 1024 * 1024
MAX_SAMPLE_PARTS = 16
MAX_SNAPSHOT_BYTES = 1024 * 1024
MIN_PUBLIC_CELL = 20
TABLES = ("vessel_tracks", "source_observations")
TIME_BASES = ("naive", "explicit_offset")
TIME_QUALITY = {*TIME_BASES, "missing", "unparseable"}
SPEED_BINS = {
    "missing", "invalid", "zero_or_imputed_missing", "0_to_1", "1_to_5",
    "5_to_15", "15_to_30", "30_to_60", "60_or_more_review",
}
SCOPE = "Evenly spaced archive objects. The sample is non-random and supports no extrapolation."
LIMITATIONS = (
    "Counts measure stored messages. Naive months use unverified local time labels. "
    "Explicit offsets are normalized to UTC. Stored zero can include imputed missing speed. "
    "Reported speed alone cannot establish vessel movement or traffic exposure."
)
MONTH = re.compile(r"(naive|explicit_offset):([0-9]{4})-(0[1-9]|1[0-2])")


def _fields(value: Any, expected: set[str]) -> None:
    if not isinstance(value, dict) or value.keys() != expected:
        raise ValueError("unexpected snapshot fields")


def _count(value: Any, ceiling: int = 2**53 - 1) -> int:
    if type(value) is not int or not 0 <= value <= ceiling:
        raise ValueError("invalid snapshot count")
    return value


def _histogram(value: Any, allowed: set[str], rows: int) -> None:
    if not isinstance(value, dict) or not value.keys() <= allowed:
        raise ValueError("unexpected histogram categories")
    if sum(_count(count, rows) for count in value.values()) != rows:
        raise ValueError("histogram row mismatch")


def validate_snapshot(snapshot: Any) -> None:
    """Reject invalid accounting or fields outside the private aggregate contract."""
    _fields(snapshot, {"method", "manifest_sha256", "sample_bytes", "status", "tables"})
    if snapshot["method"] != METHOD or snapshot["status"] != "incomplete":
        raise ValueError("unsupported snapshot method or coverage status")
    digest = snapshot["manifest_sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("invalid manifest digest")
    if not _count(snapshot["sample_bytes"], MAX_SAMPLE_BYTES):
        raise ValueError("empty byte coverage")
    tables = snapshot["tables"]
    _fields(tables, set(TABLES))
    for name, table in tables.items():
        fields = {
            "sample_parts", "total_parts", "sample_rows", "total_rows",
            "multi_month_parts", "time_quality", "calendar_months",
        }
        if name == "vessel_tracks":
            fields.add("reported_sog_knots")
        _fields(table, fields)
        parts = _count(table["sample_parts"], MAX_SAMPLE_PARTS)
        rows = _count(table["sample_rows"])
        total_parts = _count(table["total_parts"])
        total_rows = _count(table["total_rows"])
        if not 0 < parts <= total_parts or not parts <= rows <= total_rows:
            raise ValueError("invalid sample coverage")
        if parts == total_parts and rows != total_rows:
            raise ValueError("full object coverage does not reconcile")
        multi_month = _count(table["multi_month_parts"], parts)
        _histogram(table["time_quality"], TIME_QUALITY, rows)
        months = table["calendar_months"]
        if not isinstance(months, dict) or len(months) > 240_000:
            raise ValueError("invalid calendar histogram")
        by_basis: Counter[str] = Counter()
        for label, count in months.items():
            match = MONTH.fullmatch(label) if isinstance(label, str) else None
            if match is None or match[2] == "0000" or not _count(count, rows):
                raise ValueError("invalid calendar month")
            by_basis[match[1]] += count
        if any(by_basis[basis] != table["time_quality"].get(basis, 0) for basis in TIME_BASES):
            raise ValueError("calendar totals do not match time basis")
        if multi_month and (len(months) < 2 or multi_month * 2 > sum(by_basis.values())):
            raise ValueError("inconsistent multi-month coverage")
        if name == "vessel_tracks":
            _histogram(table["reported_sog_knots"], SPEED_BINS, rows)


def public_snapshot(path: Path, approved_digest: str) -> dict[str, Any]:
    """Load the exact reviewed artifact and project only coarse aggregates."""
    with path.open("rb") as snapshot_file:
        raw = snapshot_file.read(MAX_SNAPSHOT_BYTES + 1)
    if len(raw) > MAX_SNAPSHOT_BYTES or hashlib.sha256(raw).hexdigest() != approved_digest:
        raise ValueError("snapshot does not match publication approval")
    snapshot = json.loads(raw)
    validate_snapshot(snapshot)
    tables = {}
    for name, table in snapshot["tables"].items():
        if table["sample_rows"] < MIN_PUBLIC_CELL:
            raise ValueError("insufficient table coverage for publication")
        result = {key: table[key] for key in ("sample_rows", "total_rows", "sample_parts", "total_parts")}
        for key in ("time_quality", "calendar_months", "reported_sog_knots"):
            if key in table:
                histogram = table[key]
                # Withhold the whole histogram so totals cannot reveal a single hidden cell.
                result[key] = histogram if all(count == 0 or count >= MIN_PUBLIC_CELL
                                                for count in histogram.values()) else None
        # Time quality can reveal a sparse calendar subtotal for an entire time basis.
        if result["calendar_months"] is None:
            result["time_quality"] = None
        tables[name] = result
    return {"method": METHOD, "status": "incomplete", "scope": SCOPE,
            "limitations": LIMITATIONS, "tables": tables}
