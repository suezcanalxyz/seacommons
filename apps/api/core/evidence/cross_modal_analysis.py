# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass

from core.evidence.cross_modal import CrossModalEvidencePacket


def _required(value: str, field_name: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text[:max_chars]


@dataclass(frozen=True)
class ContradictionRecord:
    topic: str
    evidence_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        topic = _required(self.topic, "topic", 128)
        reason = _required(self.reason, "reason", 512)
        ids = tuple(sorted({_required(value, "evidence_id", 256) for value in self.evidence_ids}))
        if len(ids) < 2:
            raise ValueError("contradiction requires at least two distinct evidence IDs")
        object.__setattr__(self, "topic", topic)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "evidence_ids", ids)


@dataclass(frozen=True)
class CrossModalIndependenceAssessment:
    packet_id: str
    state: str
    independence_groups: tuple[str, ...]
    independent_group_count: int
    direct_evidence_count: int
    derived_evidence_count: int
    modalities: tuple[str, ...]
    contradictions: tuple[ContradictionRecord, ...]
    confidence_ceiling: float


def evaluate_independence(
    packet: CrossModalEvidencePacket,
    *,
    contradictions: tuple[ContradictionRecord, ...] = (),
) -> CrossModalIndependenceAssessment:
    if not isinstance(packet, CrossModalEvidencePacket):
        raise ValueError("packet must be CrossModalEvidencePacket")
    evidence_ids = {ref.evidence_id for ref in packet.evidence}
    normalized: dict[tuple[str, tuple[str, ...], str], ContradictionRecord] = {}
    for record in contradictions:
        if not isinstance(record, ContradictionRecord):
            raise ValueError("contradictions must contain ContradictionRecord values")
        unknown = set(record.evidence_ids) - evidence_ids
        if unknown:
            raise ValueError("contradiction references unknown evidence")
        normalized.setdefault((record.topic, record.evidence_ids, record.reason), record)
    contradiction_tuple = tuple(
        normalized[key] for key in sorted(normalized, key=lambda item: (item[0], item[1], item[2]))
    )
    direct = tuple(ref for ref in packet.evidence if not ref.derived)
    derived = tuple(ref for ref in packet.evidence if ref.derived)
    groups = packet.independence_groups
    if contradiction_tuple:
        state = "contradictory"
    elif len(groups) >= 2:
        state = "multi_lineage"
    else:
        state = "single_lineage"
    return CrossModalIndependenceAssessment(
        packet_id=packet.packet_id,
        state=state,
        independence_groups=groups,
        independent_group_count=len(groups),
        direct_evidence_count=len(direct),
        derived_evidence_count=len(derived),
        modalities=tuple(sorted({ref.modality for ref in direct})),
        contradictions=contradiction_tuple,
        confidence_ceiling=packet.confidence_ceiling,
    )
