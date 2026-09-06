from __future__ import annotations

from datetime import datetime, timezone


def _source_observation(*, observation_id: str, observation_type: str, lineage: str, receiver_id: str):
    from core.intel.source_observation import SourceObservation

    return SourceObservation(
        observation_id=observation_id,
        service="maritime",
        lane="safety",
        observation_type=observation_type,
        source_name=f"radio_receiver:{lineage}",
        source_policy="structured_remote_radio_decoder",
        source_id=f"{observation_type}:{observation_id}",
        source_url="",
        observed_at="2026-09-07T00:10:00+00:00",
        received_at="2026-09-07T00:10:01",
        raw_payload_hash="a" * 64,
        raw_payload_ref=f"artifact:{observation_id}",
        lat=None,
        lon=None,
        location_precision=None,
        uncertainty_m=None,
        subject_refs=[],
        provenance={
            "receiver_id": receiver_id,
            "physical_lineage": lineage,
            "frequency_hz": 2_187_500,
        },
        schema_version=1,
        preservation_status="source_preserved",
        replayed=False,
    )


def test_dsc_and_navtex_references_use_radio_modality_and_physical_lineage():
    from core.radio.evidence_bridge import evidence_reference_for_dsc, evidence_reference_for_navtex

    dsc = evidence_reference_for_dsc(
        _source_observation(
            observation_id="obs:dsc:1", observation_type="dsc_message",
            lineage="med_physical_1", receiver_id="kiwi_frontend",
        )
    )
    navtex = evidence_reference_for_navtex(
        _source_observation(
            observation_id="obs:navtex:1", observation_type="navtex_message",
            lineage="med_physical_2", receiver_id="owrx_frontend",
        )
    )

    assert dsc.evidence_class == "dsc_message"
    assert navtex.evidence_class == "navtex_message"
    assert dsc.modality == navtex.modality == "radio"
    assert dsc.source_lineage == "radio_receiver:med_physical_1"
    assert navtex.source_lineage == "radio_receiver:med_physical_2"
    assert dsc.independence_key == "source:radio_receiver:med_physical_1"
    assert navtex.independence_key == "source:radio_receiver:med_physical_2"


def test_two_frontends_for_one_physical_receiver_never_add_independence():
    from core.evidence.cross_modal import CrossModalEvidencePacket
    from core.radio.evidence_bridge import evidence_reference_for_dsc

    first = evidence_reference_for_dsc(
        _source_observation(
            observation_id="obs:dsc:front-a", observation_type="dsc_message",
            lineage="same_physical", receiver_id="kiwi_frontend",
        )
    )
    second = evidence_reference_for_dsc(
        _source_observation(
            observation_id="obs:dsc:front-b", observation_type="dsc_message",
            lineage="same_physical", receiver_id="owrx_frontend",
        )
    )
    packet = CrossModalEvidencePacket(subject_id="maritime:case:1", evidence=(first, second))

    assert packet.independence_groups == ("source:radio_receiver:same_physical",)


def test_radio_evidence_bridge_rejects_wrong_observation_type_or_missing_lineage():
    import pytest
    from core.radio.evidence_bridge import evidence_reference_for_dsc

    wrong = _source_observation(
        observation_id="obs:wrong", observation_type="navtex_message",
        lineage="med_physical", receiver_id="rx",
    )
    with pytest.raises(ValueError, match="dsc_message"):
        evidence_reference_for_dsc(wrong)

    missing = _source_observation(
        observation_id="obs:no-lineage", observation_type="dsc_message",
        lineage="med_physical", receiver_id="rx",
    )
    missing.provenance.clear()
    with pytest.raises(ValueError, match="physical_lineage"):
        evidence_reference_for_dsc(missing)
