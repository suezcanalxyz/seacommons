from __future__ import annotations

from datetime import datetime, timezone

import pytest


def _ref(evidence_id, *, source_lineage, modality, evidence_class, derived=False, confidence=0.8):
    from core.evidence.cross_modal import EvidenceReference
    return EvidenceReference(
        evidence_id=evidence_id,
        evidence_class=evidence_class,
        source_lineage=source_lineage,
        modality=modality,
        observed_at=datetime(2026, 9, 6, 19, 0, tzinfo=timezone.utc),
        confidence=confidence,
        derived=derived,
    )


def _packet(*refs, ceiling=0.9):
    from core.evidence.cross_modal import CrossModalEvidencePacket
    return CrossModalEvidencePacket(subject_id="incident:42", evidence=tuple(refs), confidence_ceiling=ceiling)


def test_same_physical_receiver_radio_and_audio_are_one_independent_source():
    from core.evidence.cross_modal_analysis import evaluate_independence

    packet = _packet(
        _ref("obs:radio:1", source_lineage="radio_receiver:med_rx_01", modality="radio", evidence_class="radio_signal"),
        _ref("audio:1", source_lineage="radio_receiver:med_rx_01", modality="audio", evidence_class="audio_artifact"),
    )
    result = evaluate_independence(packet)
    assert result.independence_groups == ("source:radio_receiver:med_rx_01",)
    assert result.independent_group_count == 1
    assert result.direct_evidence_count == 2


def test_multiple_ais_providers_and_derived_behaviour_stay_one_group():
    from core.evidence.cross_modal_analysis import evaluate_independence

    packet = _packet(
        _ref("ais:1", source_lineage="aisstream", modality="ais", evidence_class="ais_observation"),
        _ref("ais:2", source_lineage="aiscast", modality="ais", evidence_class="ais_observation"),
        _ref("feat:1", source_lineage="ais_sensor_lineage", modality="ais", evidence_class="ais_derived", derived=True),
    )
    result = evaluate_independence(packet)
    assert result.independence_groups == ("modality:ais",)
    assert result.independent_group_count == 1
    assert result.derived_evidence_count == 1


def test_distinct_first_party_humanitarian_sources_remain_independent():
    from core.evidence.cross_modal_analysis import evaluate_independence

    packet = _packet(
        _ref("alarm:1", source_lineage="alarm_phone", modality="humanitarian", evidence_class="operational_claim"),
        _ref("ngo:1", source_lineage="sos_mediterranee", modality="humanitarian", evidence_class="verification_claim"),
    )
    result = evaluate_independence(packet)
    assert result.independent_group_count == 2
    assert result.state == "multi_lineage"


def test_contradictions_are_preserved_not_averaged_into_confidence():
    from core.evidence.cross_modal_analysis import ContradictionRecord, evaluate_independence

    a = _ref("ngo:rescue", source_lineage="ngo_a", modality="humanitarian", evidence_class="verification_claim", confidence=0.95)
    b = _ref("ngo:no-rescue", source_lineage="ngo_b", modality="humanitarian", evidence_class="verification_claim", confidence=0.4)
    packet = _packet(a, b, ceiling=0.83)
    contradiction = ContradictionRecord(
        topic="rescue_outcome",
        evidence_ids=(a.evidence_id, b.evidence_id),
        reason="conflicting first-party outcome claims",
    )
    result = evaluate_independence(packet, contradictions=(contradiction,))
    assert result.state == "contradictory"
    assert result.contradictions == (contradiction,)
    assert result.confidence_ceiling == 0.83
    assert not hasattr(result, "average_confidence")


def test_contradiction_must_reference_evidence_in_packet():
    from core.evidence.cross_modal_analysis import ContradictionRecord, evaluate_independence

    packet = _packet(_ref("alarm:1", source_lineage="alarm_phone", modality="humanitarian", evidence_class="operational_claim"))
    contradiction = ContradictionRecord(topic="outcome", evidence_ids=("alarm:1", "missing:1"), reason="conflict")
    with pytest.raises(ValueError, match="unknown evidence"):
        evaluate_independence(packet, contradictions=(contradiction,))


def test_contradiction_record_is_bounded_and_requires_two_distinct_evidence_ids():
    from core.evidence.cross_modal_analysis import ContradictionRecord

    with pytest.raises(ValueError, match="at least two"):
        ContradictionRecord(topic="x", evidence_ids=("a",), reason="conflict")
    with pytest.raises(ValueError, match="at least two"):
        ContradictionRecord(topic="x", evidence_ids=("a", "a"), reason="conflict")
    record = ContradictionRecord(topic="x" * 200, evidence_ids=("b", "a"), reason="r" * 1000)
    assert len(record.topic) == 128
    assert len(record.reason) == 512
    assert record.evidence_ids == ("a", "b")
