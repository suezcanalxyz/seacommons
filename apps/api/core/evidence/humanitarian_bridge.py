# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from core.evidence.cross_modal import CrossModalEvidencePacket
from core.evidence.cross_modal_analysis import CrossModalIndependenceAssessment


def _bounded_context(
    packet: CrossModalEvidencePacket,
    analysis: CrossModalIndependenceAssessment,
) -> dict[str, object]:
    return {
        "packet_id": packet.packet_id,
        "evidence_ids": [ref.evidence_id for ref in packet.evidence],
        "evidence_classes": sorted({ref.evidence_class for ref in packet.evidence}),
        "independent_group_count": analysis.independent_group_count,
        "modalities": list(analysis.modalities),
        "contradiction_topics": sorted({item.topic for item in analysis.contradictions}),
        "missing_evidence_classes": list(packet.missing_evidence_classes),
        "confidence_ceiling": min(packet.confidence_ceiling, analysis.confidence_ceiling),
    }


def attach_resolution_context(
    incident_id: str,
    packet: CrossModalEvidencePacket,
    analysis: CrossModalIndependenceAssessment,
) -> dict[str, object]:
    """Attach privacy-bounded cross-modal context without changing resolution semantics."""
    incident_id = str(incident_id or "").strip()
    if not incident_id or packet.subject_id != incident_id:
        raise ValueError("packet subject must match incident_id")
    if analysis.packet_id != packet.packet_id:
        raise ValueError("analysis packet_id must match packet")

    from core.db.models import AssessmentDB
    from core.db.session import session_scope
    from core.intel.resolution_assessment import (
        _row_to_dict,
        evaluate_resolution_assessment,
    )

    baseline = evaluate_resolution_assessment(incident_id)
    context = _bounded_context(packet, analysis)
    with session_scope() as db:
        row = db.get(AssessmentDB, baseline["assessment_id"])
        if row is None:
            raise RuntimeError("resolution assessment was not persisted")
        value = dict(row.value or {})
        value["cross_modal_context"] = context
        row.value = value
        db.flush()
        result = _row_to_dict(row)
    from core.observability import record_cross_modal_event

    record_cross_modal_event(stage="humanitarian_context", state=analysis.state, outcome="attached")
    return result
