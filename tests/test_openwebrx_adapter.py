from __future__ import annotations

from datetime import datetime

import pytest
from core.radio.provider import ReceiverCapability
from core.radio.registry import ReceiverDescriptor, ReceiverRegistry


class FakeTransport:
    def __init__(self, *, fail_start: bool = False):
        self.fail_start = fail_start
        self.started = False
        self.stopped = False
        self.websocket_url = ""
        self.controls: list[dict[str, object]] = []
        self.on_message = None
        self.on_disconnect = None

    def start(self, *, websocket_url, timeout_s, on_message, on_disconnect):
        if self.fail_start:
            raise OSError("offline")
        self.started = True
        self.websocket_url = websocket_url
        self.on_message = on_message
        self.on_disconnect = on_disconnect

    def send_control(self, payload):
        self.controls.append(dict(payload))

    def stop(self):
        self.stopped = True


def descriptor(*, frontend_url="https://rx.example.org/", physical_lineage="med-rx-01"):
    return ReceiverDescriptor(
        receiver_id="openwebrx_med_rx",
        provider="openwebrx",
        frontend_url=frontend_url,
        physical_lineage=physical_lineage,
        enabled=True,
        terms_status="allowed",
        source_terms="operator-permission",
        capabilities=(ReceiverCapability(100_000, 180_000_000, ("am", "usb", "lsb", "nbfm")),),
    )


def test_start_uses_ws_endpoint_and_health_transitions():
    from core.radio.openwebrx import OpenWebRXAdapter

    transport = FakeTransport()
    adapter = OpenWebRXAdapter(descriptor(), on_observation=lambda _obs: None, transport=transport)
    adapter.start()

    assert transport.websocket_url == "wss://rx.example.org/ws/"
    assert adapter.health().connected is True
    adapter.stop()
    assert transport.stopped is True
    assert adapter.health().connected is False


def test_tune_rejects_capability_before_transport_send():
    from core.radio.openwebrx import OpenWebRXAdapter

    transport = FakeTransport()
    adapter = OpenWebRXAdapter(descriptor(), on_observation=lambda _obs: None, transport=transport)
    adapter.start()

    with pytest.raises(ValueError):
        adapter.tune(190_000_000, "nbfm")
    assert transport.controls == []

    adapter.tune(156_800_000, "nbfm")
    assert transport.controls[-1] == {"type": "tune", "frequency_hz": 156_800_000, "mode": "nbfm"}


def test_signal_message_normalizes_metadata_and_discards_audio():
    from core.radio.openwebrx import OpenWebRXAdapter

    observations = []
    transport = FakeTransport()
    adapter = OpenWebRXAdapter(descriptor(), on_observation=observations.append, transport=transport)
    adapter.start()
    adapter.tune(156_800_000, "nbfm")

    assert transport.on_message is not None
    transport.on_message({"type": "signal", "signal_dbm": -83.5, "snr_db": 12.0, "message_id": "abc"})
    transport.on_message(b"pretend-audio-bytes")

    assert len(observations) == 1
    obs = observations[0]
    assert obs.receiver_id == "openwebrx_med_rx"
    assert obs.provider == "openwebrx"
    assert obs.physical_lineage == "med_rx_01"
    assert obs.frequency_hz == 156_800_000
    assert obs.mode == "nbfm"
    assert obs.signal_dbm == -83.5
    assert obs.snr_db == 12.0
    assert obs.source_terms == "operator-permission"
    assert obs.provider_message_id == "abc"


def test_disconnect_and_start_failure_fail_closed():
    from core.radio.openwebrx import OpenWebRXAdapter

    transport = FakeTransport()
    adapter = OpenWebRXAdapter(descriptor(), on_observation=lambda _obs: None, transport=transport)
    adapter.start()
    assert transport.on_disconnect is not None
    transport.on_disconnect("anything")
    assert adapter.health().connected is False
    assert adapter.health().error == "transport_disconnected"

    failing = OpenWebRXAdapter(
        descriptor(), on_observation=lambda _obs: None, transport=FakeTransport(fail_start=True)
    )
    with pytest.raises(RuntimeError, match="OpenWebRX connection failed"):
        failing.start()
    assert failing.health().connected is False
    assert failing.health().error == "connect_failed"


def test_openwebrx_and_kiwi_frontends_same_physical_receiver_are_one_runnable_lineage():
    kiwi = ReceiverDescriptor(
        receiver_id="kiwi_frontend",
        provider="kiwisdr",
        frontend_url="https://kiwi.example.org",
        physical_lineage="shared-rx-01",
        enabled=True,
        terms_status="allowed",
        source_terms="ok",
        capabilities=(ReceiverCapability(100_000, 30_000_000, ("am", "usb", "lsb")),),
    )
    owrx = descriptor(frontend_url="https://owrx.example.org", physical_lineage="shared-rx-01")

    registry = ReceiverRegistry((kiwi, owrx), max_receivers=10)
    runnable = registry.runnable()

    assert len(runnable) == 1
    assert runnable[0].physical_lineage == "shared_rx_01"


def test_message_timestamp_defaults_to_now_and_health_counts_only_signal_observations(monkeypatch):
    from core.radio.openwebrx import OpenWebRXAdapter

    observations = []
    transport = FakeTransport()
    adapter = OpenWebRXAdapter(descriptor(), on_observation=observations.append, transport=transport)
    adapter.start()
    adapter.tune(1_000_000, "am")
    assert transport.on_message is not None
    transport.on_message({"type": "status", "clients": 4})
    transport.on_message({"type": "signal", "signal_dbm": -100.0})

    assert len(observations) == 1
    assert observations[0].observed_at.tzinfo is not None
    assert adapter.health().observations_received == 1
    assert isinstance(adapter.health().last_message_at, datetime)
