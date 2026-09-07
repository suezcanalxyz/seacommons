from __future__ import annotations

from core.radio.provider import ReceiverCapability, RemoteReceiverHealth
from core.radio.registry import ReceiverDescriptor


def _descriptor(provider: str, lineage: str, suffix: str):
    return ReceiverDescriptor(
        receiver_id=f"{provider}_{suffix}",
        provider=provider,
        frontend_url=f"https://{suffix}.example.org",
        physical_lineage=lineage,
        enabled=True,
        terms_status="allowed",
        source_terms="operator-permission",
        capabilities=(ReceiverCapability(100_000, 180_000_000, ("am", "nbfm")),),
    )


class FakeAdapter:
    def __init__(self, descriptor, *, fail=False):
        self.descriptor = descriptor
        self.fail = fail
        self.started = False
        self.stopped = False
        self.tuned = []

    def start(self):
        if self.fail:
            raise RuntimeError("private endpoint detail")
        self.started = True

    def stop(self):
        self.stopped = True
        self.started = False

    def health(self):
        return RemoteReceiverHealth(
            receiver_id=self.descriptor.receiver_id,
            provider=self.descriptor.provider,
            connected=self.started,
            last_message_at=None,
            observations_received=0,
            error=None,
        )

    def capabilities(self):
        return self.descriptor.capabilities

    def tune(self, frequency_hz, mode):
        self.tuned.append((frequency_hz, mode))


def test_runtime_disabled_by_default_never_builds_adapters():
    from core.radio.runtime import RemoteRadioRuntime

    calls = []
    runtime = RemoteRadioRuntime(
        enabled=False,
        descriptors=(_descriptor("kiwisdr", "rx-1", "one"),),
        max_receivers=8,
        adapter_factory=lambda descriptor, callback: calls.append(descriptor),
    )
    runtime.start()
    assert calls == []
    assert runtime.status()["enabled"] is False
    assert runtime.status()["started"] == 0


def test_runtime_suppresses_duplicate_physical_lineage_before_adapter_start():
    from core.radio.runtime import RemoteRadioRuntime

    created = []
    descriptors = (
        _descriptor("kiwisdr", "same-rx", "kiwi"),
        _descriptor("openwebrx", "same-rx", "owrx"),
    )

    def factory(descriptor, callback):
        created.append(descriptor.provider)
        return FakeAdapter(descriptor)

    runtime = RemoteRadioRuntime(
        enabled=True, descriptors=descriptors, max_receivers=8, adapter_factory=factory
    )
    runtime.start()
    assert len(created) == 1
    assert runtime.status()["runnable"] == 1


def test_start_failure_remains_managed_and_retries_until_connected():
    from core.radio.runtime import RemoteRadioRuntime

    descriptor = _descriptor("kiwisdr", "rx-retry", "retry")

    class FlakyAdapter(FakeAdapter):
        def __init__(self, desc):
            super().__init__(desc)
            self.attempts = 0

        def start(self):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("temporary upstream outage")
            self.started = True

    adapter = FlakyAdapter(descriptor)
    runtime = RemoteRadioRuntime(
        enabled=True, descriptors=(descriptor,), max_receivers=8,
        adapter_factory=lambda _d, _cb: adapter, reconnect_interval_s=60.0,
    )
    runtime.start()
    first = runtime.status(include_receivers=True)
    assert first["started"] == 0
    assert first["failed"] == 1
    assert first["receivers"][0]["state"] == "disconnected"

    runtime._reconnect_disconnected_once()
    recovered = runtime.status(include_receivers=True)
    assert adapter.attempts == 2
    assert recovered["started"] == 1
    assert recovered["failed"] == 0
    assert recovered["receivers"][0]["state"] == "connected"


def test_partial_provider_failure_is_isolated_and_status_is_bounded():
    from core.radio.runtime import RemoteRadioRuntime

    descriptors = (
        _descriptor("kiwisdr", "rx-1", "secret-kiwi"),
        _descriptor("openwebrx", "rx-2", "secret-owrx"),
    )

    def factory(descriptor, callback):
        return FakeAdapter(descriptor, fail=descriptor.provider == "kiwisdr")

    runtime = RemoteRadioRuntime(
        enabled=True, descriptors=descriptors, max_receivers=8, adapter_factory=factory
    )
    runtime.start()
    status = runtime.status()

    assert status["started"] == 1
    assert status["failed"] == 1
    assert status["providers"]["kiwisdr"]["failed"] == 1
    assert status["providers"]["openwebrx"]["connected"] == 1
    serialized = str(status).lower()
    assert "secret-kiwi" not in serialized
    assert "secret-owrx" not in serialized
    assert "example.org" not in serialized
    assert "private endpoint detail" not in serialized


def test_stop_stops_every_started_adapter():
    from core.radio.runtime import RemoteRadioRuntime

    adapters = []

    def factory(descriptor, callback):
        adapter = FakeAdapter(descriptor)
        adapters.append(adapter)
        return adapter

    runtime = RemoteRadioRuntime(
        enabled=True,
        descriptors=(
            _descriptor("kiwisdr", "rx-1", "one"),
            _descriptor("openwebrx", "rx-2", "two"),
        ),
        max_receivers=8,
        adapter_factory=factory,
    )
    runtime.start()
    runtime.stop()

    assert all(adapter.stopped for adapter in adapters)
    assert runtime.status()["started"] == 0


def test_ops_summary_exposes_only_bounded_remote_radio_status(monkeypatch):
    from core.api.main import app
    from core.radio import runtime as radio_runtime
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        radio_runtime,
        "get_remote_radio_status",
        lambda: {
            "enabled": True,
            "configured": 2,
            "runnable": 1,
            "started": 1,
            "failed": 1,
            "providers": {"openwebrx": {"connected": 1, "failed": 0}},
        },
    )
    payload = TestClient(app).get("/api/v1/ops/summary").json()
    assert payload["backend"]["remote_radio"]["runnable"] == 1
    assert "receiver_id" not in str(payload["backend"]["remote_radio"])
    assert "frontend_url" not in str(payload["backend"]["remote_radio"])


def test_receiver_descriptor_accepts_public_channel_metadata():
    descriptor = ReceiverDescriptor(
        receiver_id="med_dsc_1", provider="kiwisdr",
        frontend_url="https://rx.example.org", physical_lineage="med_rx_1",
        enabled=True, terms_status="allowed", source_terms="operator-permission",
        capabilities=(ReceiverCapability(2_000_000, 3_000_000, ("usb", "am")),),
        public_label="Mediterranean DSC 1", channel_kind="dsc",
        frequency_hz=2_187_500, mode="usb",
    )
    assert descriptor.public_label == "Mediterranean DSC 1"
    assert descriptor.channel_kind == "dsc"
    assert descriptor.frequency_hz == 2_187_500
    assert descriptor.mode == "usb"


def test_receiver_descriptor_defaults_to_monitor_and_public_receiver_id():
    descriptor = _descriptor("kiwisdr", "rx-default", "default")
    assert descriptor.channel_kind == "monitor"
    assert descriptor.public_label == descriptor.receiver_id
    assert descriptor.frequency_hz is None
    assert descriptor.mode is None


def test_receiver_descriptor_rejects_invalid_channel_or_out_of_range_frequency():
    import pytest

    kwargs = dict(
        receiver_id="med_rx", provider="kiwisdr", frontend_url="https://rx.example.org",
        physical_lineage="med_rx", enabled=True, terms_status="allowed",
        source_terms="operator-permission",
        capabilities=(ReceiverCapability(2_000_000, 3_000_000, ("usb",)),),
        public_label="Med receiver",
    )
    with pytest.raises(ValueError, match="channel_kind"):
        ReceiverDescriptor(**kwargs, channel_kind="voice")
    with pytest.raises(ValueError, match="frequency_hz"):
        ReceiverDescriptor(**kwargs, channel_kind="dsc", frequency_hz=4_000_000, mode="usb")
    with pytest.raises(ValueError, match="requires frequency_hz"):
        ReceiverDescriptor(**kwargs, channel_kind="navtex")


def test_receiver_descriptor_public_label_is_bounded():
    descriptor = ReceiverDescriptor(
        receiver_id="label_rx", provider="kiwisdr", frontend_url="https://rx.example.org",
        physical_lineage="label_rx", enabled=True, terms_status="allowed",
        source_terms="operator-permission",
        capabilities=(ReceiverCapability(100_000, 30_000_000, ("am",)),),
        public_label="  " + ("Station " * 30) + "  ",
    )
    assert descriptor.public_label == descriptor.public_label.strip()
    assert len(descriptor.public_label) <= 96


def test_detailed_runtime_status_exposes_only_public_safe_receiver_channel_metadata():
    from core.radio.runtime import RemoteRadioRuntime

    descriptor = ReceiverDescriptor(
        receiver_id="med_dsc", provider="kiwisdr", frontend_url="https://secret.example.org/rx",
        physical_lineage="med_physical", enabled=True, terms_status="allowed",
        source_terms="private terms text",
        capabilities=(ReceiverCapability(2_000_000, 3_000_000, ("usb",)),),
        public_label="Mediterranean DSC", channel_kind="dsc", frequency_hz=2_187_500, mode="usb",
    )
    runtime = RemoteRadioRuntime(
        enabled=True, descriptors=(descriptor,), max_receivers=8,
        adapter_factory=lambda d, callback: FakeAdapter(d),
    )
    runtime.start()
    status = runtime.status(include_receivers=True)

    assert status["receivers"] == [{
        "receiver_id": "med_dsc",
        "station_label": "Mediterranean DSC",
        "provider": "kiwisdr",
        "state": "connected",
        "channel_kind": "dsc",
        "frequency_hz": 2_187_500,
        "mode": "usb",
        "last_observation_at": None,
        "observations_received": 0,
    }]
    serialized = str(status)
    assert "secret.example.org" not in serialized
    assert "private terms text" not in serialized
    assert "physical_lineage" not in serialized


def test_runtime_tunes_configured_channel_after_receiver_start():
    from core.radio.runtime import RemoteRadioRuntime

    descriptor = ReceiverDescriptor(
        receiver_id="med_dsc", provider="kiwisdr", frontend_url="https://rx.example.org",
        physical_lineage="med_rx", enabled=True, terms_status="allowed",
        source_terms="operator-permission",
        capabilities=(ReceiverCapability(2_000_000, 3_000_000, ("usb",)),),
        public_label="Mediterranean DSC", channel_kind="dsc",
        frequency_hz=2_187_500, mode="usb",
    )
    adapters = []
    def factory(desc, callback):
        adapter = FakeAdapter(desc)
        adapters.append(adapter)
        return adapter

    runtime = RemoteRadioRuntime(
        enabled=True, descriptors=(descriptor,), max_receivers=8, adapter_factory=factory,
    )
    runtime.start()

    assert adapters[0].tuned == [(2_187_500, "usb")]
    assert runtime.status()["started"] == 1


def test_runtime_reconnects_disconnected_receiver_and_restores_configured_tune():
    from core.radio.runtime import RemoteRadioRuntime

    descriptor = ReceiverDescriptor(
        receiver_id="med_dsc", provider="kiwisdr", frontend_url="https://rx.example.org",
        physical_lineage="med_rx", enabled=True, terms_status="allowed",
        source_terms="operator-permission",
        capabilities=(ReceiverCapability(2_000_000, 3_000_000, ("usb",)),),
        public_label="Mediterranean DSC", channel_kind="monitor",
        frequency_hz=2_187_500, mode="usb",
    )
    adapters = []
    def factory(desc, callback):
        adapter = FakeAdapter(desc)
        adapter.start_count = 0
        original_start = adapter.start
        def counted_start():
            adapter.start_count += 1
            original_start()
        adapter.start = counted_start
        adapters.append(adapter)
        return adapter

    runtime = RemoteRadioRuntime(
        enabled=True, descriptors=(descriptor,), max_receivers=8, adapter_factory=factory,
        reconnect_interval_s=60.0,
    )
    runtime.start()
    adapter = adapters[0]
    assert adapter.start_count == 1
    adapter.started = False

    runtime._reconnect_disconnected_once()

    assert adapter.start_count == 2
    assert adapter.started is True
    assert adapter.tuned[-1] == (2_187_500, "usb")
    runtime.stop()


def test_runtime_activates_public_pool_when_primary_cannot_start():
    from core.radio.runtime import RemoteRadioRuntime

    primary = _descriptor("kiwisdr", "primary-lineage", "primary")
    fallback = _descriptor("kiwisdr", "fallback-lineage", "fallback")
    created = []

    def factory(descriptor, callback):
        created.append(descriptor.receiver_id)
        return FakeAdapter(descriptor, fail=descriptor.receiver_id == primary.receiver_id)

    runtime = RemoteRadioRuntime(
        enabled=True,
        descriptors=(primary,),
        fallback_descriptors=(fallback,),
        max_receivers=3,
        adapter_factory=factory,
        reconnect_interval_s=60.0,
    )
    runtime.start()
    status = runtime.status(include_receivers=True)
    assert primary.receiver_id in created
    assert fallback.receiver_id in created
    assert status["started"] == 1
    assert any(row["receiver_id"] == fallback.receiver_id and row["state"] == "connected" for row in status["receivers"])


def test_runtime_activates_public_pool_alongside_live_primary():
    from core.radio.runtime import RemoteRadioRuntime

    primary = _descriptor("kiwisdr", "primary-lineage", "primary-live")
    fallback = _descriptor("kiwisdr", "fallback-lineage", "fallback-standby")
    created = []

    def factory(descriptor, callback):
        created.append(descriptor.receiver_id)
        return FakeAdapter(descriptor)

    runtime = RemoteRadioRuntime(
        enabled=True,
        descriptors=(primary,),
        fallback_descriptors=(fallback,),
        max_receivers=3,
        adapter_factory=factory,
    )
    runtime.start()
    assert created == [primary.receiver_id, fallback.receiver_id]
    assert runtime.status()["started"] == 2


def test_public_fallback_receivers_are_bounded_terms_allowed_and_monitor_only():
    from core.radio.public_pool import public_receiver_pool

    rows = public_receiver_pool()
    assert len(rows) >= 16
    for row in rows:
        assert row.enabled is True
        assert row.terms_status == "allowed"
        assert row.source_terms
        assert row.channel_kind == "monitor"
        assert row.frequency_hz == 2_187_500
        assert row.mode == "usb"
        assert row.provider in {"kiwisdr", "openwebrx"}


def test_runtime_starts_multiple_receivers_concurrently():
    import threading
    from core.radio.runtime import RemoteRadioRuntime

    barrier = threading.Barrier(2, timeout=0.5)

    class ConcurrentAdapter(FakeAdapter):
        def start(self):
            barrier.wait()
            self.started = True

    descriptors = (
        _descriptor("kiwisdr", "parallel-one", "parallel-one"),
        _descriptor("kiwisdr", "parallel-two", "parallel-two"),
    )
    runtime = RemoteRadioRuntime(
        enabled=True,
        descriptors=descriptors,
        max_receivers=2,
        adapter_factory=lambda descriptor, _callback: ConcurrentAdapter(descriptor),
        reconnect_interval_s=60.0,
    )
    runtime.start()
    assert runtime.status()["started"] == 2
    runtime.stop()
