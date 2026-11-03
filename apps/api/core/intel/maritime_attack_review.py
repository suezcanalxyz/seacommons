# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only PLAY incident review projection; never publishes or writes to DB."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from core.intel.maritime_attack_gate import AttackEvidence, evaluate_attack_candidate

ATTACK_CATEGORY = "maritime_attack"
ATTACK_COLOR = "#E05252"  # reserved for analyst-reviewed maritime attack candidates
HUMANITARIAN_CATEGORY = "humanitarian_distress"


def build_attack_review_dossier(
    evidence: list[AttackEvidence], *, ais_observations: list[dict[str, Any]] | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Pure, deterministic analyst-review dossier, not a PLAY/incident promotion."""
    result = evaluate_attack_candidate(evidence)
    observations = ais_observations or []
    signals = []
    for row in observations:
        kind = row.get("kind")
        if kind not in ("ais_gap", "sudden_stop", "ais_anomaly"):
            continue
        signals.append({
            "kind": kind, "mmsi": row.get("mmsi"), "observed_at": row.get("observed_at"),
            "source": row.get("source"), "position": row.get("position"),
            "evidence_role": "context_only_not_attack_proof",
        })
    signals.sort(key=lambda row: (str(row["observed_at"]), str(row["kind"]), str(row["mmsi"])))
    provenance = sorted(result.get("sources", []), key=lambda row: (row["id"], row["url"]))
    payload = {"sources": provenance, "signals": signals, "status": result["status"],
               "reasons": result.get("reasons", [])}
    digest = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return {
        "case_id": case_id or "attack-review-" + digest[:16],
        "category": ATTACK_CATEGORY,
        "display_color": ATTACK_COLOR,
        "humanitarian_category": HUMANITARIAN_CATEGORY,
        "review_status": result["status"],
        "play_to_incident": "blocked_pending_analyst_review",
        "automatic_publication": False,
        "attribution": None,
        "source_provenance": provenance,
        "independent_groups": result.get("independent_groups", []),
        "ais_context_signals": signals,
        "decision_reasons": result.get("reasons", []),
        "audit": {"input_sha256": digest, "decision": "review_only", "writes_performed": False},
    }
