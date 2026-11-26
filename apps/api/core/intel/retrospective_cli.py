# SPDX-License-Identifier: AGPL-3.0-or-later
"""Replay frozen private case bundles and compare detector predictions."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path

from core.evidence.cross_modal import EvidenceReference
from core.intel.retrospective_validation import ClaimEvidence, compare_detectors, validate_claim

MAX_BUNDLE_BYTES = 4 * 1024 * 1024


def _load(path: Path) -> dict:
    with path.open("rb") as handle:
        data = handle.read(MAX_BUNDLE_BYTES + 1)
    if len(data) > MAX_BUNDLE_BYTES:
        raise ValueError("research bundle exceeds size limit")
    decoded = json.loads(data)
    if not isinstance(decoded, dict):
        raise ValueError("research bundle must be a JSON object")
    return decoded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("dossier", "backtest"))
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        bundle = _load(args.bundle)
        if args.action == "dossier":
            evidence = []
            for item in bundle["evidence"]:
                reference = dict(item["reference"])
                reference["observed_at"] = datetime.fromisoformat(reference["observed_at"])
                evidence.append(ClaimEvidence(
                    EvidenceReference(**reference), item["relation"],
                    datetime.fromisoformat(item["available_at"]),
                ))
            document = asdict(validate_claim(
                bundle["episode_id"], bundle["claim_id"], tuple(evidence),
                cutoff=datetime.fromisoformat(bundle["cutoff"]),
                reviewed_by=bundle.get("reviewed_by"), review_reason=bundle.get("review_reason"),
            ))
        else:
            result = compare_detectors(bundle["truth"], bundle["baseline"], bundle["candidate"])
            document = asdict(result)
            for name in ("baseline", "candidate"):
                metrics = getattr(result, name)
                document[name].update(precision=metrics.precision, recall=metrics.recall, f1=metrics.f1)
        print(json.dumps(document, default=datetime.isoformat, indent=2, sort_keys=True))
    except (KeyError, TypeError, OSError, ValueError, RecursionError):
        parser.exit(1, "Invalid or unreadable research bundle. No result emitted.\n")


if __name__ == "__main__":
    main()
