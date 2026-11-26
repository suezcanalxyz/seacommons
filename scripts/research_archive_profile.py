#!/usr/bin/env python3
"""Bounded descriptive profile of historical archive objects; not traffic or gap inference."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any

from research_archive_sample_verify import MAX_MANIFEST_BYTES, MAX_PART_BYTES, make_reader, sample_indices, validate_manifest
from research_archive_replay import decode_verified_part, manifest_digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from core.intel.historical_snapshot import (
    MAX_SAMPLE_BYTES, MAX_SAMPLE_PARTS, METHOD, TABLES, validate_snapshot,
)


def reported_speed_class(value: Any, *, zero_verified: bool = False) -> str:
    """Classify stored SOG; legacy zero has lost its missingness provenance."""
    if value is None:
        return "missing"
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        return "invalid"
    if value == 0:
        return "zero" if zero_verified else "zero_or_imputed_missing"
    if value < 1:
        return "0_to_1"
    if value < 5:
        return "1_to_5"
    if value < 15:
        return "5_to_15"
    if value < 30:
        return "15_to_30"
    if value < 60:
        return "30_to_60"
    return "60_or_more_review"


def time_class(value: Any) -> tuple[str, str | None]:
    """Return calendar month and explicit time basis, never assume naive timestamps UTC."""
    if value is None:
        return "missing", None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return "unparseable", None
    if not isinstance(value, datetime):
        return "unparseable", None
    if value.tzinfo is None or value.utcoffset() is None:
        return "naive", value.strftime("%Y-%m")
    return "explicit_offset", value.astimezone(timezone.utc).strftime("%Y-%m")


def profile_table(table, table_name: str) -> dict[str, Any]:
    """Return additive aggregates only. No identity, position, source text or URLs."""
    timestamp = "ts" if table_name == "vessel_tracks" else "observed_at"
    times = Counter()
    months = Counter()
    for value in table[timestamp].to_pylist():
        kind, month = time_class(value)
        times[kind] += 1
        if month:
            months[f"{kind}:{month}"] += 1
    result = {"rows": table.num_rows, "time_quality": dict(times), "calendar_months": dict(months)}
    if table_name == "vessel_tracks":
        result["reported_sog_knots"] = dict(Counter(reported_speed_class(v) for v in table["sog"].to_pylist()))
    if sum(times.values()) != table.num_rows:
        raise ValueError("time accounting")
    return result


def profile_archive(manifest, get, samples: int) -> dict[str, Any]:
    if type(samples) is not int or not 1 <= samples <= MAX_SAMPLE_PARTS:
        raise ValueError("sample part budget")
    validate_manifest(manifest)
    if json.loads(get(manifest["prefix"] + "/manifest.json", MAX_MANIFEST_BYTES)) != manifest:
        raise ValueError("remote manifest differs")
    report = {}
    transferred = 0
    for name in TABLES:
        parts = manifest["tables"][name]["parts"]
        indices = sample_indices(len(parts), samples)
        counters = {k: Counter() for k in ("time_quality", "calendar_months", "reported_sog_knots")}
        rows = 0
        multi_month_parts = 0
        for index in indices:
            part = parts[index]
            if part["bytes"] > MAX_PART_BYTES or transferred + part["bytes"] > MAX_SAMPLE_BYTES:
                raise ValueError("sample byte budget")
            table = decode_verified_part(part, get(part["key"], MAX_PART_BYTES))
            summary = profile_table(table, name)
            rows += summary["rows"]
            transferred += part["bytes"]
            multi_month_parts += len(summary["calendar_months"]) > 1
            for key in counters:
                counters[key].update(summary.get(key, {}))
        if rows != sum(parts[i]["rows"] for i in indices):
            raise ValueError("sample row accounting")
        if name != "vessel_tracks":
            del counters["reported_sog_knots"]
        report[name] = {"sample_parts": len(indices), "total_parts": len(parts), "sample_rows": rows,
                        "total_rows": manifest["tables"][name]["rows"], "multi_month_parts": multi_month_parts,
                        **{k: dict(v) for k, v in counters.items()}}
    snapshot = {"method": METHOD, "manifest_sha256": manifest_digest(manifest),
                "sample_bytes": transferred, "status": "incomplete", "tables": report}
    validate_snapshot(snapshot)
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path.home()/".config/seacommons/r2.env")
    parser.add_argument("--samples", type=int, default=9)
    args = parser.parse_args()
    if not 1 <= args.samples <= MAX_SAMPLE_PARTS:
        parser.error(f"sample budget 1–{MAX_SAMPLE_PARTS} objects per table")
    try:
        if args.manifest.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("manifest budget")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        print(json.dumps(profile_archive(manifest, make_reader(args.config), args.samples), indent=2, sort_keys=True))
    except Exception as exc:
        parser.exit(1, f"Profile failed ({type(exc).__name__}); no partial result emitted.\n")


if __name__ == "__main__":
    main()
