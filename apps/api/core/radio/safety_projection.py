# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib

from core.intel.store import IntelEvent, intel_store
from core.radio.structured import DSCObservation


def _candidate_id(observation: DSCObservation) -> str:
    material = f"{observation.physical_lineage}:{observation.decoder_message_id}"
    digest = hashlib.blake2s(material.encode("utf-8"), digest_size=10).hexdigest()
    return f"dscsafe:{digest}"


def project_dsc_safety_candidate(
    observation: DSCObservation,
    *,
    evidence_observation_id: str,
) -> IntelEvent | None:
    """Project only DSC distress into the existing Maritime Safety event path."""
    if observation.category != "distress":
        return None
    evidence_id = str(evidence_observation_id or "").strip()
    if not evidence_id:
        raise ValueError("evidence_observation_id is required")

    candidate_id = _candidate_id(observation)
    return IntelEvent(
        id=candidate_id,
        timestamp_utc=observation.observed_at.isoformat(),
        type="dsc_distress",
        severity="critical",
        lat=observation.latitude,
        lon=observation.longitude,
        title="DSC distress received",
        text=f"Decoded DSC distress candidate; operator review required. Ref {candidate_id}.",
        source=f"radio_receiver:{observation.physical_lineage}",
        linked_mmsi=observation.mmsi or "",
        metadata={
            "service": "maritime",
            "lane": "safety",
            "maritime_domain": "safety",
            "is_distress": True,
            "dsc_category": observation.category,
            "dsc_nature_code": observation.nature_code or "",
            "receiver_id": observation.receiver_id,
            "physical_lineage": observation.physical_lineage,
            "frequency_hz": observation.frequency_hz,
            "evidence_observation_id": evidence_id,
            "raw_evidence_ref": observation.raw_evidence_ref,
            "review_required": True,
        },
    )


def ingest_dsc_safety_candidate(
    observation: DSCObservation,
    *,
    evidence_observation_id: str,
) -> bool:
    event = project_dsc_safety_candidate(
        observation,
        evidence_observation_id=evidence_observation_id,
    )
    if event is None:
        return False
    return intel_store.add(event, dedup_key=event.id)
