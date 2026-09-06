from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone

import pytest


def _ref(**overrides):
    from core.evidence.cross_modal import EvidenceReference

    values = {
        "evidence_id": "obs:alarm:1",
        "evidence_class": "operational_claim",
        "source_lineage": "alarm_phone",
        "modality": "humanitarian",
        "observed_at": datetime(2026, 9, 6, 18, 0, tzinfo=timezone.utc),
        "confidence": 0.9,
        "derived": False,
    }
    values.update(overrides)
    return EvidenceReference(**values)


def test_evidence_reference_is_frozen_normalized_and_deterministic():
    first = _ref(source_lineage="Alarm Phone")
    second = _ref(source_lineage="alarm_phone")
    assert first == second
    assert first.independence_key == "source:alarm_phone"
    with pytest.raises(FrozenInstanceError):
        first.confidence = 0.2  # type: ignore[misc]


def test_reference_vocab_and_confidence_fail_closed():
    with pytest.raises(ValueError, match="evidence_class"):
        _ref(evidence_class="magic")
    with pytest.raises(ValueError, match="modality"):
        _ref(modality="magic")
    with pytest.raises(ValueError, match="confidence"):
        _ref(confidence=1.1)
    with pytest.raises(ValueError, match="timezone"):
        _ref(observed_at=datetime(2026, 9, 6, 18, 0))


def test_all_ais_providers_share_one_modality_independence_group():
    aisstream = _ref(
        evidence_id="obs:aisstream:1", evidence_class="ais_observation",
        source_lineage="aisstream", modality="ais",
    )
    aiscast = _ref(
        evidence_id="obs:aiscast:1", evidence_class="ais_observation",
        source_lineage="aiscast", modality="ais",
    )
    assert aisstream.independence_key == "modality:ais"
    assert aiscast.independence_key == "modality:ais"


def test_derived_evidence_never_has_an_independence_key():
    transcript = _ref(
        evidence_id="atr:1", evidence_class="audio_transcript",
        source_lineage="radio_receiver:med_rx_01", modality="audio", derived=True,
    )
    behaviour = _ref(
        evidence_id="feat:ais:1", evidence_class="ais_derived",
        source_lineage="ais_sensor_lineage", modality="ais", derived=True,
    )
    assert transcript.independence_key is None
    assert behaviour.independence_key is None


def test_packet_collapses_duplicate_lineage_and_derived_evidence():
    from core.evidence.cross_modal import CrossModalEvidencePacket

    refs = (
        _ref(),
        _ref(evidence_id="obs:alarm:2"),
        _ref(evidence_id="obs:ngo:1", evidence_class="verification_claim", source_lineage="sos_mediterranee"),
        _ref(evidence_id="obs:ais:1", evidence_class="ais_observation", source_lineage="aisstream", modality="ais"),
        _ref(evidence_id="obs:ais:2", evidence_class="ais_observation", source_lineage="aiscast", modality="ais"),
        _ref(evidence_id="atr:1", evidence_class="audio_transcript", source_lineage="radio_receiver:rx1", modality="audio", derived=True),
    )
    packet = CrossModalEvidencePacket(
        subject_id="incident:123",
        evidence=refs,
        required_evidence_classes=("operational_claim", "verification_claim", "dsc_message"),
        contradictions=("rescue_outcome_conflict",),
        confidence_ceiling=0.72,
    )
    assert packet.independence_groups == (
        "modality:ais",
        "source:alarm_phone",
        "source:sos_mediterranee",
    )
    assert packet.missing_evidence_classes == ("dsc_message",)
    assert packet.contradictions == ("rescue_outcome_conflict",)
    assert packet.confidence_ceiling == 0.72


def test_packet_identity_is_order_independent_and_no_truth_authority_fields_exist():
    from core.evidence.cross_modal import CrossModalEvidencePacket

    a = _ref()
    b = _ref(evidence_id="obs:ngo:1", evidence_class="verification_claim", source_lineage="sea_watch")
    one = CrossModalEvidencePacket(subject_id="incident:1", evidence=(a, b))
    two = CrossModalEvidencePacket(subject_id="incident:1", evidence=(b, a))
    assert one.packet_id == two.packet_id
    names = {f.name for f in fields(type(one))}
    for forbidden in ("lifecycle", "publication", "decision", "resolution", "humanitarian_status"):
        assert forbidden not in names


def test_packet_required_classes_and_contradictions_are_bounded_and_deduped():
    from core.evidence.cross_modal import CrossModalEvidencePacket

    packet = CrossModalEvidencePacket(
        subject_id="incident:1",
        evidence=(_ref(),),
        required_evidence_classes=("verification_claim", "verification_claim"),
        contradictions=("x", "x"),
        confidence_ceiling=0.5,
    )
    assert packet.required_evidence_classes == ("verification_claim",)
    assert packet.contradictions == ("x",)
    with pytest.raises(ValueError, match="confidence_ceiling"):
        CrossModalEvidencePacket(subject_id="incident:1", evidence=(_ref(),), confidence_ceiling=2.0)
