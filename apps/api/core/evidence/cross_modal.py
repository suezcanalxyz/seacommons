# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime

_EVIDENCE_CLASSES = frozenset({
    "operational_claim", "verification_claim", "archive_reference",
    "ais_observation", "ais_derived", "dsc_message", "navtex_message",
    "radio_signal", "audio_artifact", "audio_transcript", "satellite_observation",
})
_MODALITIES = frozenset({"humanitarian", "ais", "radio", "audio", "satellite", "documentary"})
_MAX_EVIDENCE = 128
_MAX_CONTRADICTIONS = 32


def _required(value: str, field_name: str, max_chars: int = 256) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text[:max_chars]


def _lineage(value: str) -> str:
    text = _required(value, "source_lineage", 128).lower()
    text = re.sub(r"[^a-z0-9:_-]+", "_", text).strip("_")
    if not text:
        raise ValueError("source_lineage must not be empty")
    return text


@dataclass(frozen=True)
class EvidenceReference:
    evidence_id: str
    evidence_class: str
    source_lineage: str
    modality: str
    observed_at: datetime
    confidence: float
    derived: bool = False
    independence_key: str | None = field(init=False)

    def __post_init__(self) -> None:
        evidence_id = _required(self.evidence_id, "evidence_id", 256)
        evidence_class = str(self.evidence_class or "").strip().lower()
        if evidence_class not in _EVIDENCE_CLASSES:
            raise ValueError("evidence_class is not in the bounded vocabulary")
        modality = str(self.modality or "").strip().lower()
        if modality not in _MODALITIES:
            raise ValueError("modality is not in the bounded vocabulary")
        lineage = _lineage(self.source_lineage)
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.derived:
            key = None
        elif modality == "ais":
            key = "modality:ais"
        else:
            key = f"source:{lineage}"
        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "evidence_class", evidence_class)
        object.__setattr__(self, "source_lineage", lineage)
        object.__setattr__(self, "modality", modality)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "independence_key", key)


@dataclass(frozen=True)
class CrossModalEvidencePacket:
    subject_id: str
    evidence: tuple[EvidenceReference, ...]
    required_evidence_classes: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    confidence_ceiling: float = 1.0
    packet_id: str = field(init=False)
    independence_groups: tuple[str, ...] = field(init=False)
    missing_evidence_classes: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        subject_id = _required(self.subject_id, "subject_id", 256)
        refs_by_id: dict[str, EvidenceReference] = {}
        for ref in self.evidence:
            if not isinstance(ref, EvidenceReference):
                raise ValueError("evidence must contain EvidenceReference values")
            refs_by_id.setdefault(ref.evidence_id, ref)
        if not refs_by_id:
            raise ValueError("evidence must not be empty")
        if len(refs_by_id) > _MAX_EVIDENCE:
            raise ValueError("evidence exceeds bounded packet size")
        evidence = tuple(sorted(refs_by_id.values(), key=lambda item: item.evidence_id))

        required: set[str] = set()
        for value in self.required_evidence_classes:
            item = str(value or "").strip().lower()
            if item not in _EVIDENCE_CLASSES:
                raise ValueError("required_evidence_classes contains unknown evidence_class")
            required.add(item)
        required_tuple = tuple(sorted(required))

        contradictions: set[str] = set()
        for value in self.contradictions:
            item = _required(value, "contradiction", 128)
            contradictions.add(item)
        if len(contradictions) > _MAX_CONTRADICTIONS:
            raise ValueError("contradictions exceed bounded packet size")
        contradictions_tuple = tuple(sorted(contradictions))

        ceiling = float(self.confidence_ceiling)
        if not 0.0 <= ceiling <= 1.0:
            raise ValueError("confidence_ceiling must be between 0 and 1")

        groups = tuple(sorted({ref.independence_key for ref in evidence if ref.independence_key}))
        present = {ref.evidence_class for ref in evidence}
        missing = tuple(item for item in required_tuple if item not in present)
        material = {
            "subject_id": subject_id,
            "evidence": [
                [r.evidence_id, r.evidence_class, r.source_lineage, r.modality,
                 r.observed_at.isoformat(), r.confidence, r.derived]
                for r in evidence
            ],
            "required": required_tuple,
            "contradictions": contradictions_tuple,
            "confidence_ceiling": ceiling,
        }
        encoded = json.dumps(material, sort_keys=True, separators=(",", ":"))
        packet_id = "xev:" + hashlib.blake2s(encoded.encode("utf-8"), digest_size=16).hexdigest()
        object.__setattr__(self, "subject_id", subject_id)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "required_evidence_classes", required_tuple)
        object.__setattr__(self, "contradictions", contradictions_tuple)
        object.__setattr__(self, "confidence_ceiling", ceiling)
        object.__setattr__(self, "packet_id", packet_id)
        object.__setattr__(self, "independence_groups", groups)
        object.__setattr__(self, "missing_evidence_classes", missing)
