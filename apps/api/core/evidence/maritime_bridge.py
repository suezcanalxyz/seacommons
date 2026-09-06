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


def attach_episode_context(
    episode_id: str,
    packet: CrossModalEvidencePacket,
    analysis: CrossModalIndependenceAssessment,
):
    """Attach bounded cross-modal context to a persisted MaritimeEpisode only."""
    episode_id = str(episode_id or "").strip()
    if not episode_id or packet.subject_id != episode_id:
        raise ValueError("packet subject must match episode_id")
    if analysis.packet_id != packet.packet_id:
        raise ValueError("analysis packet_id must match packet")

    from core.db.models import MaritimeEpisodeDB
    from core.db.session import session_scope

    with session_scope() as db:
        row = db.get(MaritimeEpisodeDB, episode_id)
        if row is None:
            raise ValueError("maritime episode not found")
        behaviour = dict(row.behaviour_context or {})
        behaviour["cross_modal_context"] = _bounded_context(packet, analysis)
        row.behaviour_context = behaviour
        db.flush()
        db.refresh(row)
        db.expunge(row)
    from core.observability import record_cross_modal_event

    record_cross_modal_event(stage="maritime_context", state=analysis.state, outcome="attached")
    return row
