#!/usr/bin/env python3
"""Read-only PLAY catalog census. Aggregate only; no IDs, locations or source text.
Two matching scans are a consistency check, NOT a transaction-pinned snapshot.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import time
from urllib.request import urlopen

FIELDS = ("domain", "main_category", "case_type", "incident_status",
          "verification_status", "evidence_state", "episode_family",
          "hypothesis_state", "archive_source")
PAGE_SIZE = 500


def scan(fetch, max_pages=100, pause=0.1):
    counts = {field: Counter() for field in FIELDS}
    flags = Counter()
    by_domain_status = Counter()
    signatures = {}
    offset = 0
    expected = None
    for _ in range(max_pages):
        page = fetch(offset)
        total = page["total_count"]
        items = page["incidents"]
        if type(total) is not int or total < 0 or page["offset"] != offset:
            raise ValueError("invalid page metadata")
        if expected is None:
            expected = total
        if total != expected or len(items) > PAGE_SIZE:
            raise ValueError("catalog changed or invalid page size")
        for row in items:
            ident = row.get("incident_id")
            if not isinstance(ident, str) or not ident or ident in signatures:
                raise ValueError("missing or repeated catalog identity")
            values = [row.get(field) for field in FIELDS]
            relevant = values + [row.get("corroborated"), row.get("has_satellite"),
                                 row.get("last_update_at"), row.get("state_changed_at")]
            signatures[ident] = hashlib.sha256(
                json.dumps(relevant, sort_keys=True).encode()
            ).hexdigest()
            for field, value in zip(FIELDS, values):
                counts[field][str(value) if value is not None else "unknown"] += 1
            by_domain_status[f"{row.get('domain')} / {row.get('incident_status')}"] += 1
            for key in ("corroborated", "has_satellite"):
                value = row.get(key)
                flags[f"{key}:{'true' if value is True else 'false' if value is False else 'unknown'}"] += 1
            if row.get("domain") != row.get("main_category"):
                flags["domain_category_disagreement"] += 1
        next_offset = page["next_offset"]
        if next_offset is None:
            if len(signatures) != expected:
                raise ValueError("incomplete catalog")
            digest = hashlib.sha256(json.dumps(sorted(signatures.items())).encode()).hexdigest()
            result = {"total": expected, "counts": {k: dict(v) for k, v in counts.items()},
                      "flags": dict(flags), "domain_status": dict(by_domain_status)}
            return result, digest
        if type(next_offset) is not int or not items or next_offset != offset + len(items):
            raise ValueError("non-contiguous pagination")
        offset = next_offset
        time.sleep(pause)
    raise ValueError("page budget exhausted")


def census(fetch, **kwargs):
    first, digest = scan(fetch, **kwargs)
    second, second_digest = scan(fetch, **kwargs)
    if first != second or digest != second_digest:
        raise ValueError("catalog changed between scans; retry later")
    return {"schema_version": 1, "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "PLAY catalog only; matching scans, not a pinned database snapshot",
            "consistency": "two matching scans of IDs and selected fields",
            **second}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--max-pages", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.max_pages <= 1000:
        parser.error("invalid port or page budget")

    def fetch(offset):
        url = f"http://127.0.0.1:{args.port}/api/v1/play/incidents?limit={PAGE_SIZE}&offset={offset}"
        with urlopen(url, timeout=15) as response:
            return json.load(response)

    try:
        print(json.dumps(census(fetch, max_pages=args.max_pages), sort_keys=True, indent=2))
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Census failed: unavailable or inconsistent catalog; no partial result emitted.\n")


if __name__ == "__main__":
    main()
