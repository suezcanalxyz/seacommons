from __future__ import annotations

from datetime import datetime, timezone


def _ctx():
    return {
        "receiver_id": "owrx_med_rx",
        "physical_lineage": "med_rx_01",
        "observed_at": datetime(2026, 9, 6, 19, 0, tzinfo=timezone.utc),
        "source_terms": "operator-permission",
        "raw_evidence_ref": "artifact:decoded:1",
    }


def test_runtime_disabled_by_default_rejects_input_without_side_effects():
    from core.radio.structured_runtime import StructuredRadioRuntime

    runtime = StructuredRadioRuntime(enabled=False)
    result = runtime.ingest_dsc({"category": "distress", "message_id": "x"}, frequency_hz=2_187_500, **_ctx())
    assert result == {"accepted": False, "reason": "disabled"}
    assert runtime.status()["enabled"] is False
    assert runtime.status()["accepted"] == 0


def test_enabled_runtime_persists_dsc_and_projects_only_distress():
    from core.db.session import session_scope
    from core.radio.structured_runtime import StructuredRadioRuntime

    with session_scope() as db:
        from core.db.models import HumanitarianIncidentDB
        before_incidents = db.query(HumanitarianIncidentDB).count()

    runtime = StructuredRadioRuntime(enabled=True)
    result = runtime.ingest_dsc(
        {"category": "distress", "message_id": "dsc-runtime-1", "mmsi": "123456789", "latitude": 35.5, "longitude": 14.2},
        frequency_hz=2_187_500,
        **_ctx(),
    )
    assert result["accepted"] is True
    assert result["projected"] is True
    assert result["observation_id"].startswith("obs:")
    ref = result["evidence_reference"]
    assert ref.evidence_id == result["observation_id"]
    assert ref.evidence_class == "dsc_message"
    assert ref.modality == "radio"
    assert ref.source_lineage == "radio_receiver:med_rx_01"
    assert runtime.status()["accepted"] == 1

    with session_scope() as db:
        from core.db.models import HumanitarianIncidentDB
        assert db.query(HumanitarianIncidentDB).count() == before_incidents


def test_enabled_runtime_navtex_is_context_only():
    from core.radio.structured_runtime import StructuredRadioRuntime

    runtime = StructuredRadioRuntime(enabled=True)
    result = runtime.ingest_navtex(
        "ZCZC MB42\nDISTRESS TRAFFIC REPORTED IN AREA.\nNNNN",
        frequency_hz=518_000,
        decoder_message_id="navtex-runtime-1",
        **_ctx(),
    )
    assert result["accepted"] is True
    assert result["projected"] is False
    assert "candidate_id" not in result
    ref = result["evidence_reference"]
    assert ref.evidence_class == "navtex_message"
    assert ref.modality == "radio"
    assert ref.source_lineage == "radio_receiver:med_rx_01"


def test_structured_radio_metrics_are_bounded_against_hostile_labels():
    from prometheus_client import generate_latest
    from core import observability

    secret = "123456789-receiver@example.com-station-Z-body-DISTRESS"
    observability.record_structured_radio_event(kind=secret, outcome=secret)
    metrics = generate_latest().decode()
    assert secret not in metrics
    assert 'seacommons_structured_radio_events_total{kind="other",outcome="other"}' in metrics
