#!/usr/bin/env python3
"""Privacy-safe hourly audit for SeaCommons public Live/Play classification.

The audit never changes case classification and never writes coordinates. Vessel class is
context only: pleasure/passenger/ferry/fishing/tug cases are surfaced for review rather
than suppressed, matching docs/fixes.md M4.3.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

LIVE_URL = "https://live.seacommons.org/api/v1/live/signals?limit=150&days=2&mode=all"
PLAY_URL = "https://play.seacommons.org/api/v1/live/archives?limit=60"
VALID_FAMILIES = {"humanitarian", "maritime"}
CONTEXT_CLASSES = ("pleasure", "passenger", "ferry", "fishing", "tug")
INFERENCE_TYPES = ("ais_gap", "dark", "spoof", "loiter", "position_integrity", "rendezvous", "transfer")


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "SeaCommons-night-watch/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def features(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("features", "archives", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def props(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("properties")
    return value if isinstance(value, dict) else item


def first_text(p: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = p.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def safe_id(p: dict[str, Any]) -> str:
    raw = first_text(p, "event_id", "incident_id", "id", "case_id", "archive_id")
    if not raw:
        return "(no public id)"
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", raw)[:80]


def classify(items: list[dict[str, Any]], surface: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    reviews: list[dict[str, str]] = []
    for item in items:
        p = props(item)
        event_id = safe_id(p)
        family = first_text(p, "maritime_domain", "domain", "family").lower()
        incident_type = first_text(p, "incident_type", "type", "kind", "category").lower()
        vessel_class = first_text(
            p,
            "ship_type_label",
            "vessel_type_label",
            "vessel_type",
            "ship_type",
            "vessel_class",
        )
        vessel_lower = vessel_class.lower()

        if not family:
            findings.append({"surface": surface, "id": event_id, "kind": "missing_family", "detail": incident_type or "unknown type"})
        elif family not in VALID_FAMILIES:
            findings.append({"surface": surface, "id": event_id, "kind": "unknown_family", "detail": family})

        if not incident_type:
            findings.append({"surface": surface, "id": event_id, "kind": "missing_case_type", "detail": family or "unknown family"})

        if vessel_lower and any(token in vessel_lower for token in CONTEXT_CLASSES):
            review_reason = "context vessel class"
            if any(token in incident_type for token in INFERENCE_TYPES):
                review_reason += " on inferred maritime case"
            reviews.append({
                "surface": surface,
                "id": event_id,
                "vessel": vessel_class,
                "type": incident_type or "unknown",
                "reason": review_reason,
            })
    return findings, reviews


def legend_findings(repo_root: Path) -> list[dict[str, str]]:
    path = repo_root / "apps/web/src/components/Legend.jsx"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    required = {
        "Humanitarian / distress": "Humanitarian family row",
        "Maritime warning / context": "Maritime family row",
        "#ff3b3b": "Humanitarian red",
    }
    findings = []
    for needle, label in required.items():
        if needle not in text:
            findings.append({"surface": "UI", "id": "Legend.jsx", "kind": "legend_mismatch", "detail": label})
    return findings


def render_markdown(now: str, counts: dict[str, int], findings: list[dict[str, str]], reviews: list[dict[str, str]], errors: list[str]) -> str:
    lines = [
        "# SeaCommons night-watch case audit",
        "",
        f"Updated: {now}",
        "",
        "Privacy-safe review only: no coordinates or current distress locations are recorded. Vessel class is contextual and never an automatic exclusion.",
        "",
        "## Snapshot",
        "",
        f"- Live public records inspected: {counts.get('live', 0)}",
        f"- Play/archive public records inspected: {counts.get('play', 0)}",
        f"- Classification findings: {len(findings)}",
        f"- Vessel-class context reviews: {len(reviews)}",
    ]
    if errors:
        lines += ["", "## Fetch/runtime warnings", ""] + [f"- {error}" for error in errors]

    lines += ["", "## Classification findings", ""]
    if findings:
        lines.append("| Surface | Public ID | Check | Detail |")
        lines.append("| --- | --- | --- | --- |")
        for row in findings:
            lines.append(f"| {row['surface']} | `{row['id']}` | {row['kind']} | {row['detail']} |")
    else:
        lines.append("No family/type/legend contract mismatch detected in this snapshot.")

    lines += ["", "## Vessel-class context review", ""]
    if reviews:
        lines.append("| Surface | Public ID | Vessel class | Case type | Reason |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in reviews:
            lines.append(f"| {row['surface']} | `{row['id']}` | {row['vessel']} | {row['type']} | {row['reason']} |")
    else:
        lines.append("No pleasure/passenger/ferry/fishing/tug cases surfaced for contextual review in this snapshot.")

    lines += [
        "",
        "## Review rule",
        "",
        "Pleasure/passenger/ferry/fishing/tug are not suppressed. If they appear in an inferred Maritime case, reviewers should check coverage context, motion pattern, location context and corroborating lineages before deciding whether the case is noise.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="night-watch-report.md")
    parser.add_argument("--json-output", default="night-watch-report.json")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    counts = {"live": 0, "play": 0}
    all_findings: list[dict[str, str]] = []
    all_reviews: list[dict[str, str]] = []
    errors: list[str] = []

    for surface, url in (("Live", LIVE_URL), ("Play", PLAY_URL)):
        try:
            payload = fetch_json(url)
            rows = features(payload)
            counts[surface.lower()] = len(rows)
            findings, reviews = classify(rows, surface)
            all_findings.extend(findings)
            all_reviews.extend(reviews)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            errors.append(f"{surface}: {type(exc).__name__}: {exc}")

    all_findings.extend(legend_findings(Path(args.repo_root)))
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    report = render_markdown(now, counts, all_findings, all_reviews, errors)
    Path(args.output).write_text(report, encoding="utf-8")
    Path(args.json_output).write_text(json.dumps({
        "updated_at": now,
        "counts": counts,
        "findings": all_findings,
        "context_reviews": all_reviews,
        "errors": errors,
    }, indent=2, sort_keys=True), encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
