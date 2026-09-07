from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from core.radio.provider import ReceiverCapability
from core.radio.registry import ReceiverDescriptor


class FakeKiwiTransport:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.fail_start = fail_start
        self.started_url: str | None = None
        self.timeout_s: float | None = None
        self.on_frame = None
        self.on_disconnect = None
        self.sent: list[str] = []
        self.stopped = False

    def start(self, *, websocket_url, timeout_s, on_frame, on_disconnect) -> None:
        if self.fail_start:
            raise OSError("remote detail that must not leak")
        self.started_url = websocket_url
        self.timeout_s = timeout_s
        self.on_frame = on_frame
        self.on_disconnect = on_disconnect

    def send(self, message: str) -> None:
        self.sent.append(message)

    def stop(self) -> None:
        self.stopped = True

    def emit(self, frame: bytes) -> None:
        assert self.on_frame is not None
        self.on_frame(frame)

    def disconnect(self, detail: str = "arbitrary remote error") -> None:
        assert self.on_disconnect is not None
        self.on_disconnect(detail)


def _descriptor() -> ReceiverDescriptor:
    return ReceiverDescriptor(
        provider="kiwisdr",
        frontend_url="https://Kiwi.Example/",
        physical_lineage="central-med-hf-01",
        capabilities=(
            ReceiverCapability(
                frequency_min_hz=10_000,
                frequency_max_hz=30_000_000,
                modes=("am", "usb", "lsb", "nbfm"),
            ),
        ),
        source_terms="https://kiwi.example/terms",
        terms_status="allowed",
    )


def _snd_frame(*, sequence: int = 7, smeter: int = 550, audio: bytes = b"audio-bytes") -> bytes:
    # Kiwi SND frame: tag + flags + LE sequence + BE S-meter + audio payload.
    return b"SND" + b"\x00" + sequence.to_bytes(4, "little") + smeter.to_bytes(2, "big") + audio


def test_start_normalizes_frontend_to_snd_websocket_and_sends_auth():
    from core.radio.kiwisdr import KiwiSDRAdapter

    transport = FakeKiwiTransport()
    adapter = KiwiSDRAdapter(
        _descriptor(),
        on_observation=lambda observation: None,
        transport=transport,
        connect_timeout_s=4.5,
        stream_id_factory=lambda: 123456789,
    )

    adapter.start()

    assert transport.started_url == "wss://kiwi.example/123456789/SND"
    assert transport.timeout_s == 4.5
    assert transport.sent[0] == "SET auth t=kiwi p="
    assert adapter.health().connected is True
    assert adapter.health().error is None


def test_tune_is_bounded_by_capability_and_kiwi_hardware_before_send():
    from core.radio.kiwisdr import KiwiSDRAdapter

    transport = FakeKiwiTransport()
    adapter = KiwiSDRAdapter(_descriptor(), on_observation=lambda observation: None, transport=transport)
    adapter.start()
    sent_before = list(transport.sent)

    with pytest.raises(ValueError, match="capability"):
        adapter.tune(31_000_000, "am")
    with pytest.raises(ValueError, match="mode"):
        adapter.tune(518_000, "iq")

    assert transport.sent == sent_before

    adapter.tune(518_000, "am")
    assert re.fullmatch(
        r"SET mod=am low_cut=-4900 high_cut=4900 freq=518(?:\.0+)?",
        transport.sent[-1],
    )


def test_snd_frame_emits_only_bounded_signal_metadata_with_source_terms():
    from core.radio.kiwisdr import KiwiSDRAdapter

    seen = []
    transport = FakeKiwiTransport()
    adapter = KiwiSDRAdapter(_descriptor(), on_observation=seen.append, transport=transport)
    adapter.start()
    adapter.tune(518_000, "am")
    transport.emit(_snd_frame(sequence=42, smeter=600, audio=b"secret voice bytes"))

    assert len(seen) == 1
    observation = seen[0]
    assert observation.receiver_id == _descriptor().receiver_id
    assert observation.provider == "kiwisdr"
    assert observation.physical_lineage == "central_med_hf_01"
    assert observation.frequency_hz == 518_000
    assert observation.mode == "am"
    assert observation.signal_dbm == pytest.approx(-67.0)
    assert observation.source_terms == "https://kiwi.example/terms"
    assert observation.provider_message_id == "42"
    assert not hasattr(observation, "audio")
    assert "secret voice bytes" not in repr(observation)
    health = adapter.health()
    assert health.observations_received == 1
    assert isinstance(health.last_message_at, datetime)
    assert health.last_message_at.tzinfo == timezone.utc


def test_transport_disconnect_and_connect_failure_fail_closed_with_bounded_errors():
    from core.radio.kiwisdr import KiwiSDRAdapter

    transport = FakeKiwiTransport()
    adapter = KiwiSDRAdapter(_descriptor(), on_observation=lambda observation: None, transport=transport)
    adapter.start()
    transport.disconnect("secret upstream hostname: password=abc")
    health = adapter.health()
    assert health.connected is False
    assert health.error == "transport_disconnected"
    assert "password" not in repr(health)

    failing = KiwiSDRAdapter(
        _descriptor(),
        on_observation=lambda observation: None,
        transport=FakeKiwiTransport(fail_start=True),
    )
    with pytest.raises(RuntimeError, match="connection failed"):
        failing.start()
    assert failing.health().connected is False
    assert failing.health().error == "connect_failed"


def test_stop_closes_transport_and_marks_health_disconnected():
    from core.radio.kiwisdr import KiwiSDRAdapter

    transport = FakeKiwiTransport()
    adapter = KiwiSDRAdapter(_descriptor(), on_observation=lambda observation: None, transport=transport)
    adapter.start()
    adapter.stop()

    assert transport.stopped is True
    assert adapter.health().connected is False
    assert adapter.health().error is None


def test_snd_audio_bytes_do_not_persist_source_observation_or_humanitarian_incident():
    from core.db.models import HumanitarianIncidentDB, SourceObservationDB
    from core.db.session import engine, session_scope
    from core.radio.kiwisdr import KiwiSDRAdapter

    for table in (SourceObservationDB.__table__, HumanitarianIncidentDB.__table__):
        table.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        before_observations = db.query(SourceObservationDB).count()
        before_incidents = db.query(HumanitarianIncidentDB).count()

    transport = FakeKiwiTransport()
    adapter = KiwiSDRAdapter(_descriptor(), on_observation=lambda observation: None, transport=transport)
    adapter.start()
    adapter.tune(518_000, "am")
    transport.emit(_snd_frame(audio=b"never persist me"))

    with session_scope() as db:
        assert db.query(SourceObservationDB).count() == before_observations
        assert db.query(HumanitarianIncidentDB).count() == before_incidents


def test_audio_init_completes_kiwi_handshake_and_reapplies_configured_tune():
    from core.radio.kiwisdr import KiwiSDRAdapter

    transport = FakeKiwiTransport()
    adapter = KiwiSDRAdapter(_descriptor(), on_observation=lambda observation: None, transport=transport)
    adapter.start()
    adapter.tune(2_187_500, "usb")

    transport.emit(b"MSG audio_init=0 audio_rate=12000")

    assert "SET AR OK in=12000 out=12000" in transport.sent
    assert "SERVER DE CLIENT SeaCommons SND" in transport.sent
    assert "SET compression=0" in transport.sent
    assert any(message.startswith("SET agc=1 ") for message in transport.sent)
    tune_messages = [message for message in transport.sent if message.startswith("SET mod=usb ")]
    assert len(tune_messages) >= 2
