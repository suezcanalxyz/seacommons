#!/usr/bin/env python3
"""Build a historical SQLite index from public SeaCommons humanitarian cases."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from urllib.parse import quote, urlencode
from urllib.request import urlopen

API = "https://play.seacommons.org/api/v1/play/incidents"


def iter_cases():
    offset = 0
    seen = set()
    while offset is not None:
        query = urlencode({"limit": 500, "offset": offset, "domain": "humanitarian"})
        with urlopen(f"{API}?{query}", timeout=30) as response:
            page = json.load(response)
        if page.get("offset") != offset:
            raise ValueError(f"Unexpected archive offset: {page.get('offset')!r}")
        for item in page["incidents"]:
            case_id = item["incident_id"]
            if item.get("domain") == "humanitarian" and case_id not in seen:
                seen.add(case_id)
                yield item
        next_offset = page["next_offset"]
        if next_offset is not None and next_offset <= offset:
            raise ValueError("The public archive stopped advancing")
        offset = next_offset


def export_archive(output, max_age_boundary, satellite_case_ids=()):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as folder:
        snapshot = Path(folder) / "archive.sqlite"
        with sqlite3.connect(snapshot) as db:
            db.executescript("""
                PRAGMA foreign_keys = ON;
                CREATE TABLE humanitarian_cases (
                    case_id TEXT PRIMARY KEY, title TEXT, case_type TEXT,
                    status TEXT, reported_at_utc TEXT NOT NULL, updated_at_utc TEXT,
                    resolved_at_utc TEXT, source TEXT, dossier_url TEXT NOT NULL
                );
                CREATE INDEX cases_by_date ON humanitarian_cases(reported_at_utc);
                CREATE INDEX cases_by_source ON humanitarian_cases(source);
                CREATE TABLE status_history (
                    case_id TEXT NOT NULL REFERENCES humanitarian_cases(case_id),
                    at_utc TEXT NOT NULL, previous_status TEXT, new_status TEXT
                );
                CREATE INDEX history_by_case ON status_history(case_id, at_utc);
                CREATE TABLE satellite_scenes (
                    case_id TEXT NOT NULL REFERENCES humanitarian_cases(case_id),
                    observation_id TEXT NOT NULL, product_id TEXT NOT NULL,
                    acquired_at_utc TEXT NOT NULL, source_url TEXT,
                    PRIMARY KEY (case_id, observation_id)
                );
                CREATE TABLE archive_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            for item in iter_cases():
                case_id = item["incident_id"]
                reported = item.get("reported_at")
                if not reported:
                    continue
                stamp = datetime.fromisoformat(reported.replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                if stamp >= max_age_boundary:
                    continue
                db.execute("INSERT INTO humanitarian_cases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    case_id, item.get("title"), item.get("case_type"), item.get("incident_status"),
                    stamp.astimezone(timezone.utc).isoformat(), item.get("last_update_at"),
                    item.get("resolved_at"), item.get("source"), f"{API}/{quote(case_id, safe='')}/timeline",
                ))
                db.executemany("INSERT INTO status_history VALUES (?, ?, ?, ?)", [
                    (case_id, row["at"], row.get("from_state"), row.get("to_state"))
                    for row in item.get("status_history", []) if row.get("at")
                ])
            if satellite_case_ids:
                from play_satellite_analysis import case_timeline, scenes

                for case_id in dict.fromkeys(satellite_case_ids):
                    if not db.execute("SELECT 1 FROM humanitarian_cases WHERE case_id = ?", (case_id,)).fetchone():
                        raise ValueError(f"Case {case_id} is outside the exported humanitarian archive")
                    db.executemany("INSERT INTO satellite_scenes VALUES (?, ?, ?, ?, ?)", (
                        (case_id, scene["observation_id"], scene["product_id"], scene["acquired_at"], scene["source_url"])
                        for scene in scenes(case_id, case_timeline(case_id))
                    ))
            metadata = {"source_api": API, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                        "reported_before_utc": max_age_boundary.isoformat(),
                        "status_semantics": "Current public archive status at export, not a historical reconstruction",
                        "satellite_scope": json.dumps(list(dict.fromkeys(satellite_case_ids))),
                        "satellite_semantics": "Catalog scenes for selected dossiers; coverage alone does not corroborate a case"}
            db.executemany("INSERT INTO archive_metadata VALUES (?, ?)", metadata.items())
            stats = db.execute("SELECT count(*), min(reported_at_utc), max(reported_at_utc) FROM humanitarian_cases").fetchone()
        db.close()
        snapshot.replace(output)
    return stats


if __name__ == "__main__":
    from datetime import timedelta

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--satellite-case", action="append", default=[], metavar="CASE_ID",
                        help="Index Sentinel-1 scene records for this archived case; repeat as needed")
    args = parser.parse_args()
    boundary = datetime.now(timezone.utc) - timedelta(hours=24)
    count, oldest, newest = export_archive(args.output, boundary, args.satellite_case)
    print(json.dumps({"cases": count, "oldest": oldest, "newest": newest}))
