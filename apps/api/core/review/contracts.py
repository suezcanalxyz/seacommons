# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime

_TARGET_TYPES = frozenset({"humanitarian_resolution", "maritime_hypothesis"})
_DECISIONS = frozenset({"approve", "reject", "needs_more_evidence"})
_TRANSITIONS = {
    "humanitarian_resolution": frozenset({"active", "resolved", "needs_review"}),
    "maritime_hypothesis": frozenset({"candidate", "collecting", "assessed", "rejected"}),
}
_FORBIDDEN_SNAPSHOT_PREFIXES = ("raw:", "mmsi:", "imo:", "callsign:", "transcript:")


def _required(value: str, field_name: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text[:max_chars]


def _identifier(value: str, field_name: str, max_chars: int = 256) -> str:
    text = _required(value, field_name, max_chars).lower()
    text = re.sub(r"[^a-z0-9:_-]+", "_", text).strip("_")
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


@dataclass(frozen=True)
class ReviewRecord:
    target_type: str
    target_id: str
    target_version: str
    evidence_snapshot_id: str
    decision: str
    rationale: str
    actor: str
    reviewed_at: datetime
    requested_transition: str | None = None
    review_id: str = field(init=False)

    def __post_init__(self) -> None:
        target_type = str(self.target_type or "").strip().lower()
        if target_type not in _TARGET_TYPES:
            raise ValueError("target_type is not supported")
        target_id = _required(self.target_id, "target_id", 256)
        target_version = _required(self.target_version, "target_version", 128)
        snapshot = _required(self.evidence_snapshot_id, "evidence_snapshot_id", 256)
        if snapshot.lower().startswith(_FORBIDDEN_SNAPSHOT_PREFIXES):
            raise ValueError("evidence_snapshot_id must be an opaque reference, not raw or sensitive evidence")
        decision = str(self.decision or "").strip().lower()
        if decision not in _DECISIONS:
            raise ValueError("decision is not supported")
        rationale = _required(self.rationale, "rationale", 2000)
        actor = _identifier(self.actor, "actor", 256)
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")

        transition_raw = str(self.requested_transition or "").strip().lower()
        transition: str | None = transition_raw or None
        if decision == "approve" and transition is None:
            raise ValueError("requested_transition is required for approve")
        if transition is not None and transition not in _TRANSITIONS[target_type]:
            raise ValueError("requested_transition is not allowed for target_type")
        if decision != "approve" and transition is not None:
            raise ValueError("requested_transition is only allowed for approve")

        material = {
            "target_type": target_type,
            "target_id": target_id,
            "target_version": target_version,
            "evidence_snapshot_id": snapshot,
            "decision": decision,
            "rationale": rationale,
            "actor": actor,
            "reviewed_at": self.reviewed_at.isoformat(),
            "requested_transition": transition,
        }
        encoded = json.dumps(material, sort_keys=True, separators=(",", ":"))
        review_id = "review:" + hashlib.blake2s(encoded.encode("utf-8"), digest_size=16).hexdigest()

        object.__setattr__(self, "target_type", target_type)
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "target_version", target_version)
        object.__setattr__(self, "evidence_snapshot_id", snapshot)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "rationale", rationale)
        object.__setattr__(self, "actor", actor)
        object.__setattr__(self, "requested_transition", transition)
        object.__setattr__(self, "review_id", review_id)
