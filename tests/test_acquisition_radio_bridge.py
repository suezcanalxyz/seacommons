from __future__ import annotations

from datetime import datetime, timezone


def _radio_observation():
    from core.radio.provider import RadioObservation

    return RadioObservation(
        receiver_id="med_rx_1",
        provider="kiwisdr",
        physical_lineage="med_physical_1",
        frequency_hz=2_187_500,
        mode="usb",
        observed_at=datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc),
        source_terms="operator-permission",
        provider_message_id="signal-1",
    )


def test_plain_radio_observation_persists_without_structured_routing(monkeypatch):
    from core.radio import bridge

    persisted = []
    structured_calls = []
    monkeypatch.setattr(bridge, "_persist_radio_observation", lambda observation: persisted.append(observation.receiver_id))
    monkeypatch.setattr(bridge, "get_structured_radio_runtime", lambda: structured_calls.append("unexpected"))

    bridge.handle_radio_observation(_radio_observation())

    assert persisted == ["med_rx_1"]
    assert structured_calls == []


def test_explicit_decoded_dsc_routes_once_to_shared_structured_runtime(monkeypatch):
    from core.radio.bridge import handle_decoded_radio_message
    from core.radio.provider import DecodedRadioMessage

    class FakeStructured:
        def __init__(self):
            self.calls = []

        def ingest_dsc(self, payload, **context):
            self.calls.append((payload, context))
            return {"accepted": True, "projected": True, "observation_id": "obs:dsc"}

    runtime = FakeStructured()
    monkeypatch.setattr("core.radio.bridge.get_structured_radio_runtime", lambda: runtime)
    message = DecodedRadioMessage(
        kind="dsc",
        receiver_id="med_rx_1",
        provider="kiwisdr",
        physical_lineage="med_physical_1",
        frequency_hz=2_187_500,
        mode="usb",
        observed_at=datetime(2026, 9, 7, 0, 1, tzinfo=timezone.utc),
        payload={"category": "distress", "message_id": "decoded-1"},
        provider_message_id="decoded-1",
        source_terms="operator-permission",
    )

    result = handle_decoded_radio_message(message)

    assert result["accepted"] is True
    assert len(runtime.calls) == 1
    payload, context = runtime.calls[0]
    assert payload["category"] == "distress"
    assert context["receiver_id"] == "med_rx_1"
    assert context["physical_lineage"] == "med_physical_1"
    assert context["frequency_hz"] == 2_187_500


def test_explicit_decoded_navtex_routes_once_to_shared_structured_runtime(monkeypatch):
    from core.radio.bridge import handle_decoded_radio_message
    from core.radio.provider import DecodedRadioMessage

    class FakeStructured:
        def __init__(self):
            self.calls = []

        def ingest_navtex(self, block, **context):
            self.calls.append((block, context))
            return {"accepted": True, "projected": False, "observation_id": "obs:navtex"}

    runtime = FakeStructured()
    monkeypatch.setattr("core.radio.bridge.get_structured_radio_runtime", lambda: runtime)
    message = DecodedRadioMessage(
        kind="navtex",
        receiver_id="med_rx_2",
        provider="openwebrx",
        physical_lineage="med_physical_2",
        frequency_hz=518_000,
        mode="am",
        observed_at=datetime(2026, 9, 7, 0, 2, tzinfo=timezone.utc),
        payload="ZCZC MB42\nDISTRESS TRAFFIC REPORTED IN AREA.\nNNNN",
        provider_message_id="navtex-1",
        source_terms="operator-permission",
    )

    result = handle_decoded_radio_message(message)

    assert result["accepted"] is True
    assert len(runtime.calls) == 1
    block, context = runtime.calls[0]
    assert block.startswith("ZCZC MB42")
    assert context["decoder_message_id"] == "navtex-1"


def test_decoded_message_rejects_kind_payload_mismatch():
    import pytest
    from core.radio.provider import DecodedRadioMessage

    common = dict(
        receiver_id="med_rx", provider="kiwisdr", physical_lineage="med_rx",
        frequency_hz=2_187_500, mode="usb",
        observed_at=datetime(2026, 9, 7, 0, 3, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError, match="DSC payload"):
        DecodedRadioMessage(kind="dsc", payload="raw audio", **common)
    with pytest.raises(ValueError, match="NAVTEX payload"):
        DecodedRadioMessage(kind="navtex", payload={"text": "not a block"}, **common)
