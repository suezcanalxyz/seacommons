# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime

from core.evidence.cross_modal import EvidenceReference
from core.intel.source_observation import SourceObservation


def _reference(
    observation: SourceObservation,
    *,
    expected_type: str,
    evidence_class: str,
    confidence: float,
) -> EvidenceReference:
    if observation.observation_type != expected_type:
        raise ValueError(f"observation_type must be {expected_type}")
    lineage = str((observation.provenance or {}).get("physical_lineage") or "").strip()
    if not lineage:
        raise ValueError("physical_lineage is required")
    observed_at = datetime.fromisoformat(str(observation.observed_at).replace("Z", "+00:00"))
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return EvidenceReference(
        evidence_id=observation.observation_id,
        evidence_class=evidence_class,
        source_lineage=f"radio_receiver:{lineage}",
        modality="radio",
        observed_at=observed_at,
        confidence=confidence,
        derived=False,
    )


def evidence_reference_for_dsc(
    observation: SourceObservation, *, confidence: float = 1.0
) -> EvidenceReference:
    return _reference(
        observation,
        expected_type="dsc_message",
        evidence_class="dsc_message",
        confidence=confidence,
    )


def evidence_reference_for_navtex(
    observation: SourceObservation, *, confidence: float = 1.0
) -> EvidenceReference:
    return _reference(
        observation,
        expected_type="navtex_message",
        evidence_class="navtex_message",
        confidence=confidence,
    )
