from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _tables():
    from core.db.models import AssessmentDB, ClaimDB, CorrelationDecisionDB, HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import engine, session_scope
    for table in (ClaimDB.__table__, CorrelationDecisionDB.__table__, AssessmentDB.__table__, HumanitarianIncidentDB.__table__, IncidentTransitionDB.__table__):
        table.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(AssessmentDB).delete()
        db.query(CorrelationDecisionDB).delete()
        db.query(ClaimDB).delete()
        db.query(IncidentTransitionDB).delete()
        db.query(HumanitarianIncidentDB).delete()
    yield


def _ref(evidence_id, *, evidence_class, source_lineage, modality, derived=False):
    from core.evidence.cross_modal import EvidenceReference
    return EvidenceReference(
        evidence_id=evidence_id,
        evidence_class=evidence_class,
        source_lineage=source_lineage,
        modality=modality,
        observed_at=datetime(2026, 9, 6, 19, 30, tzinfo=timezone.utc),
        confidence=0.8,
        derived=derived,
    )


def _packet(incident_id="incident-x"):
    from core.evidence.cross_modal import CrossModalEvidencePacket
    return CrossModalEvidencePacket(
        subject_id=incident_id,
        evidence=(
            _ref("ais:1", evidence_class="ais_observation", source_lineage="aisstream", modality="ais"),
            _ref("feat:ais:1", evidence_class="ais_derived", source_lineage="ais_sensor_lineage", modality="ais", derived=True),
            _ref("atr:1", evidence_class="audio_transcript", source_lineage="radio_receiver:secret_rx", modality="audio", derived=True),
        ),
        required_evidence_classes=("operational_claim", "verification_claim"),
        confidence_ceiling=0.7,
    )


def test_bridge_attaches_bounded_context_without_changing_resolution_outcome():
    from core.evidence.cross_modal_analysis import evaluate_independence
    from core.evidence.humanitarian_bridge import attach_resolution_context

    packet = _packet()
    result = attach_resolution_context("incident-x", packet, evaluate_independence(packet))
    assert result["value"]["outcome"] == "no_resolution_evidence"
    context = result["value"]["cross_modal_context"]
    assert context["packet_id"] == packet.packet_id
    assert context["evidence_ids"] == ["ais:1", "atr:1", "feat:ais:1"]
    assert context["evidence_classes"] == ["ais_derived", "ais_observation", "audio_transcript"]
    assert context["independent_group_count"] == 1
    assert context["modalities"] == ["ais"]
    assert context["missing_evidence_classes"] == ["operational_claim", "verification_claim"]
    assert context["confidence_ceiling"] == 0.7
    serialized = str(context).lower()
    assert "secret_rx" not in serialized
    assert "receiver" not in serialized
    assert "mmsi" not in serialized


def test_ais_and_audio_derived_context_cannot_confirm_rescue():
    from core.evidence.cross_modal_analysis import evaluate_independence
    from core.evidence.humanitarian_bridge import attach_resolution_context

    packet = _packet("incident-derived")
    result = attach_resolution_context("incident-derived", packet, evaluate_independence(packet))
    assert result["value"]["outcome"] == "no_resolution_evidence"
    assert result["confidence"] == 0.2
    assert result["review_state"] == "unreviewed"


def test_bridge_rejects_packet_for_different_incident():
    from core.evidence.cross_modal_analysis import evaluate_independence
    from core.evidence.humanitarian_bridge import attach_resolution_context

    packet = _packet("incident-a")
    with pytest.raises(ValueError, match="subject"):
        attach_resolution_context("incident-b", packet, evaluate_independence(packet))


def test_bridge_preserves_contradiction_topics_without_changing_canonical_outcome():
    from core.evidence.cross_modal import CrossModalEvidencePacket
    from core.evidence.cross_modal_analysis import ContradictionRecord, evaluate_independence
    from core.evidence.humanitarian_bridge import attach_resolution_context

    a = _ref("ngo:a", evidence_class="verification_claim", source_lineage="ngo_a", modality="humanitarian")
    b = _ref("ngo:b", evidence_class="verification_claim", source_lineage="ngo_b", modality="humanitarian")
    packet = CrossModalEvidencePacket(subject_id="incident-c", evidence=(a, b))
    contradiction = ContradictionRecord(topic="rescue_outcome", evidence_ids=("ngo:a", "ngo:b"), reason="conflict")
    analysis = evaluate_independence(packet, contradictions=(contradiction,))
    result = attach_resolution_context("incident-c", packet, analysis)
    assert result["value"]["outcome"] == "no_resolution_evidence"
    assert result["value"]["cross_modal_context"]["contradiction_topics"] == ["rescue_outcome"]


def test_bridge_does_not_create_incident_or_lifecycle_transition():
    from core.db.models import HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import session_scope
    from core.evidence.cross_modal_analysis import evaluate_independence
    from core.evidence.humanitarian_bridge import attach_resolution_context

    packet = _packet("incident-side-effects")
    with session_scope() as db:
        before_i = db.query(HumanitarianIncidentDB).count()
        before_t = db.query(IncidentTransitionDB).count()
    attach_resolution_context("incident-side-effects", packet, evaluate_independence(packet))
    with session_scope() as db:
        assert db.query(HumanitarianIncidentDB).count() == before_i
        assert db.query(IncidentTransitionDB).count() == before_t
