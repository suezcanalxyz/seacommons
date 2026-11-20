#!/usr/bin/env python3
"""Build or summarize a review queue for SeaCommons SAR detector runs."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

FIELDS = (
    "candidate_id", "incident_id", "product_id", "acquired_at", "source_url",
    "longitude", "latitude", "pixel_column", "pixel_row", "preview", "geotiff",
    "decision", "evidence_reference", "notes",
)
DECISIONS = {"vessel", "non_vessel", "inconclusive"}


def build_queue(runs, output, previous=None):
    candidates = {}
    if previous is not None:
        summarize(previous)
        with previous.open(newline="", encoding="utf-8") as handle:
            candidates.update((row["candidate_id"], row) for row in csv.DictReader(handle))
    for path in runs:
        run = json.loads(path.read_text())
        scene = run["scene"]
        for feature in run["features"]:
            candidate_id = feature["id"]
            props = feature["properties"]
            longitude, latitude = feature["geometry"]["coordinates"]
            row = {
                "candidate_id": candidate_id,
                "incident_id": scene.get("incident_id"),
                "product_id": scene["product_id"],
                "acquired_at": scene["acquired_at"],
                "source_url": scene.get("source_url"),
                "longitude": longitude,
                "latitude": latitude,
                "pixel_column": props["peak_pixel"]["column"],
                "pixel_row": props["peak_pixel"]["row"],
                "preview": str((path.parent / props["preview"]).resolve()),
                "geotiff": str((path.parent / props["geotiff"]).resolve()),
            }
            prior = candidates.setdefault(candidate_id, row)
            # A return can be exported in multiple runs or linked to several cases.
            # Preserve each case link without counting a return more than once.
            if prior is not row and row["incident_id"]:
                ids = set((prior["incident_id"] or "").split("|")) - {""}
                prior["incident_id"] = "|".join(sorted(ids | {row["incident_id"]}))
    with output.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(candidates.values())


def summarize(path):
    counts = Counter()
    seen = set()
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            candidate_id = row["candidate_id"]
            if not candidate_id or candidate_id in seen:
                raise ValueError(f"Missing or duplicate candidate ID: {candidate_id!r}")
            seen.add(candidate_id)
            decision = row["decision"].strip().lower()
            if decision and decision not in DECISIONS:
                raise ValueError(f"Unknown decision for {candidate_id}: {decision!r}")
            if decision in {"vessel", "non_vessel"} and not row["evidence_reference"].strip():
                raise ValueError(f"A conclusive review needs a source reference: {candidate_id}")
            counts[decision or "pending"] += 1
    resolved = counts["vessel"] + counts["non_vessel"]
    return {
        "candidates": len(seen),
        **{state: counts[state] for state in ("pending", "inconclusive", "vessel", "non_vessel")},
        "resolved_review_share": counts["vessel"] / resolved if resolved else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    queue = commands.add_parser("queue")
    queue.add_argument("output", type=Path)
    queue.add_argument("runs", type=Path, nargs="+")
    queue.add_argument("--previous", type=Path, help="Carry forward reviewed and pending rows")
    report = commands.add_parser("summarize")
    report.add_argument("queue", type=Path)
    args = parser.parse_args()
    if args.command == "queue":
        build_queue(args.runs, args.output, args.previous)
    else:
        print(json.dumps(summarize(args.queue), indent=2))


if __name__ == "__main__":
    main()
