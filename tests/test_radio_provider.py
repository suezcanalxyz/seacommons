from __future__ import annotations

from datetime import datetime, timezone

import pytest


def _observation(*, receiver_id: str, provider: str, physical_lineage: str):
    from core.radio.provider import RadioObservation

    return RadioObservation(
        receiver_id=receiver_id,
        provider=provider,
        physical_lineage=physical_lineage,
        frequency_hz=156_800_000,
        mode="fm",
        observed_at=datetime.now(timezone.utc),
        signal_dbm=-72.5,
        snr_db=13.0,
        source_terms="provider terms",
        provider_message_id="msg-1",
        session_id="session-1",
    )


def test_provider_name_normalizes_deterministically():
    from core.radio.provider import normalize_provider_name

    assert normalize_provider_name(" Open WebRX ") == "open_webrx"
    assert normalize_provider_name("Kiwi-SDR") == "kiwi_sdr"


def test_empty_receiver_identity_fails_closed():
    from core.radio.provider import RadioObservation

    with pytest.raises(ValueError, match="receiver_id"):
        RadioObservation(
            receiver_id=" !!! ",
            provider="kiwisdr",
            physical_lineage="receiver-site-a",
            frequency_hz=156_800_000,
            mode="fm",
            observed_at=datetime.now(timezone.utc),
        )


def test_distinct_frontends_may_share_one_physical_lineage():
    kiwi = _observation(
        receiver_id="central-med-kiwi",
        provider="kiwisdr",
        physical_lineage="central-med-rx-01",
    )
    openwebrx = _observation(
        receiver_id="central-med-openwebrx",
        provider="openwebrx",
        physical_lineage="central-med-rx-01",
    )

    assert kiwi.receiver_id != openwebrx.receiver_id
    assert kiwi.provider != openwebrx.provider
    assert kiwi.physical_lineage == openwebrx.physical_lineage == "central_med_rx_01"


def test_capability_rejects_inverted_frequency_range():
    from core.radio.provider import ReceiverCapability

    with pytest.raises(ValueError, match="frequency"):
        ReceiverCapability(
            frequency_min_hz=162_000_000,
            frequency_max_hz=156_000_000,
            modes=("fm",),
        )


def test_adapter_protocol_exposes_start_stop_health_capabilities_and_tune():
    from core.radio.provider import (
        ReceiverCapability,
        RemoteReceiverAdapter,
        RemoteReceiverHealth,
    )

    class FakeAdapter:
        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def health(self) -> RemoteReceiverHealth:
            return RemoteReceiverHealth(
                receiver_id="rx-a",
                provider="kiwisdr",
                connected=False,
                last_message_at=None,
                observations_received=0,
            )

        def capabilities(self) -> tuple[ReceiverCapability, ...]:
            return (
                ReceiverCapability(
                    frequency_min_hz=100_000,
                    frequency_max_hz=30_000_000,
                    modes=("am", "usb"),
                ),
            )

        def tune(self, frequency_hz: int, mode: str) -> None:
            return None

    assert isinstance(FakeAdapter(), RemoteReceiverAdapter)
