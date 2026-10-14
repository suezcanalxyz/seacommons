from datetime import datetime, timezone


def _frame(payload=b"\x00\x00\x01\x00"):
    from core.radio.decoder_runtime import EphemeralRadioFrame
    return EphemeralRadioFrame(
        receiver_id="rx1", provider="kiwisdr", physical_lineage="lineage1",
        frequency_hz=2_187_500, mode="usb",
        observed_at=datetime(2026, 9, 7, 13, 0, tzinfo=timezone.utc),
        sample_rate_hz=12_000, encoding="kiwi_snd_raw", payload=payload,
        source_terms="allowed",
    )


def test_ephemeral_frame_is_bounded_and_never_serializes_payload_publicly():
    frame = _frame()
    assert frame.payload == b"\x00\x00\x01\x00"
    public = frame.public_metadata()
    assert public["receiver_id"] == "rx1"
    assert "payload" not in public
    assert "lineage1" not in str(public)


def test_oversized_ephemeral_frame_is_rejected():
    import pytest
    with pytest.raises(ValueError, match="payload"):
        _frame(b"x" * 262145)


def test_disabled_decoder_runtime_drops_ephemeral_frames():
    from core.radio.decoder_runtime import RadioDecoderRuntime
    calls = []
    runtime = RadioDecoderRuntime(enabled=False, decoded_handler=lambda msg: calls.append(msg))
    result = runtime.ingest_frame(_frame())
    assert result == {"accepted": False, "reason": "disabled"}
    assert calls == []


def test_decoder_output_routes_only_valid_structured_messages():
    from core.radio.decoder_runtime import RadioDecoderRuntime
    calls = []

    class FakeDecoder:
        def decode(self, frame):
            return ({"kind": "dsc", "payload": {"category": "distress", "mmsi": "123456789"}, "message_id": "m1"},)

    runtime = RadioDecoderRuntime(
        enabled=True, decoders=(FakeDecoder(),), decoded_handler=lambda msg: calls.append(msg) or {"accepted": True}
    )
    result = runtime.ingest_frame(_frame())
    assert result["decoded"] == 1
    assert calls[0].kind == "dsc"
    assert calls[0].provider_message_id == "m1"


def test_invalid_decoder_output_is_fail_closed():
    from core.radio.decoder_runtime import RadioDecoderRuntime
    class BadDecoder:
        def decode(self, frame):
            return ({"kind": "dsc", "payload": "raw audio"},)
    runtime = RadioDecoderRuntime(enabled=True, decoders=(BadDecoder(),), decoded_handler=lambda msg: {"accepted": True})
    result = runtime.ingest_frame(_frame())
    assert result["decoded"] == 0
    assert result["invalid"] == 1


def test_decoder_submit_queue_is_bounded_and_tracks_drops():
    import time

    from core.radio.decoder_runtime import RadioDecoderRuntime

    class SlowDecoder:
        def decode(self, frame):
            time.sleep(0.05)
            return ()

    runtime = RadioDecoderRuntime(
        enabled=True, decoders=(SlowDecoder(),), decoded_handler=lambda msg: {}, queue_size=1
    )
    runtime.start()
    accepted = [runtime.submit_frame(_frame(bytes([i % 255]))) for i in range(10)]
    runtime.stop()
    assert any(value is False for value in accepted)
    assert runtime.status()["dropped"] >= 1


def test_process_decoder_jsonl_protocol_returns_structured_output(tmp_path):
    import sys

    from core.radio.decoder_runtime import JSONLProcessDecoder

    script = tmp_path / "decoder.py"
    script.write_text(
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " d=json.loads(line); print(json.dumps({'messages':[{'kind':'navtex','payload':'ZCZC KA01\\nTEST\\nNNNN','message_id':'n1'}]}), flush=True)\n"
    )
    decoder = JSONLProcessDecoder((sys.executable, str(script)), timeout_s=5.0)
    outputs = tuple(decoder.decode(_frame()))
    decoder.close()
    assert outputs[0]["kind"] == "navtex"
    assert outputs[0]["message_id"] == "n1"


def test_kiwi_audio_frame_taps_ephemeral_decoder_only_after_audio_init(monkeypatch):
    from core.radio import decoder_runtime
    from core.radio.kiwisdr import KiwiSDRAdapter

    from tests.test_kiwisdr_adapter import FakeKiwiTransport, _descriptor, _snd_frame

    frames = []
    monkeypatch.setattr(decoder_runtime, "submit_ephemeral_frame", lambda frame: frames.append(frame) or True)
    transport = FakeKiwiTransport()
    adapter = KiwiSDRAdapter(_descriptor(), on_observation=lambda obs: None, transport=transport)
    adapter.start(); adapter.tune(2_187_500, "usb")
    transport.emit(_snd_frame(audio=b"before"))
    assert frames == []
    transport.emit(b"MSG audio_init=0 audio_rate=12000")
    transport.emit(_snd_frame(audio=b"after"))
    assert frames[-1].payload == b"after"
    assert frames[-1].sample_rate_hz == 12000
    assert frames[-1].encoding == "kiwi_snd_raw"


def test_openwebrx_audio_binary_taps_ephemeral_decoder(monkeypatch):
    from core.radio import decoder_runtime
    from core.radio.openwebrx import OpenWebRXAdapter

    from tests.test_openwebrx_adapter import (
        FakeTransport,
        descriptor,
    )

    frames = []
    monkeypatch.setattr(decoder_runtime, "submit_ephemeral_frame", lambda frame: frames.append(frame) or True)
    transport = FakeTransport()
    adapter = OpenWebRXAdapter(descriptor(), on_observation=lambda obs: None, transport=transport)
    adapter.start(); transport.on_message({"type": "config", "value": {"center_freq": 2_200_000, "samp_rate": 200_000, "audio_compression": "none"}})
    adapter.tune(2_187_500, "usb")
    transport.on_message(b"\x02payload")
    assert frames[-1].payload == b"payload"
    assert frames[-1].sample_rate_hz == 12000
    assert frames[-1].encoding == "openwebrx_pcm_s16le"


def test_openwebrx_compressed_audio_is_not_forwarded_to_pcm_decoder(monkeypatch):
    from core.radio import decoder_runtime
    from core.radio.openwebrx import OpenWebRXAdapter

    from tests.test_openwebrx_adapter import FakeTransport, descriptor

    frames = []
    monkeypatch.setattr(decoder_runtime, "submit_ephemeral_frame", lambda frame: frames.append(frame) or True)
    transport = FakeTransport()
    adapter = OpenWebRXAdapter(descriptor(), on_observation=lambda obs: None, transport=transport)
    adapter.start()
    transport.on_message({"type": "config", "value": {"center_freq": 2_200_000, "samp_rate": 200_000, "audio_compression": "adpcm"}})
    adapter.tune(2_187_500, "usb")
    transport.on_message(b"\x02compressed")
    assert frames == []


def test_decoder_worker_survives_downstream_handler_error():
    import time

    from core.radio.decoder_runtime import RadioDecoderRuntime

    class FakeDecoder:
        def decode(self, frame):
            return ({
                "kind": "dsc",
                "payload": {"category": "routine"},
                "message_id": "m1",
            },)

    runtime = RadioDecoderRuntime(
        enabled=True,
        decoders=(FakeDecoder(),),
        decoded_handler=lambda _msg: (_ for _ in ()).throw(RuntimeError("persist failed")),
        queue_size=2,
    )
    runtime.start()
    assert runtime.submit_frame(_frame()) is True
    deadline = time.time() + 1.0
    while runtime.status()["frames"] < 1 and time.time() < deadline:
        time.sleep(0.01)
    status = runtime.status()
    assert status["worker_alive"] is True
    assert status["errors"] >= 1
    assert status["decoded"] == 0
    runtime.stop()


def test_frequency_filtered_decoder_skips_incompatible_frame_without_process_start():
    import sys

    from core.radio.decoder_runtime import JSONLProcessDecoder

    decoder = JSONLProcessDecoder(
        (sys.executable, "/definitely/not/a/decoder.py"),
        accepted_frequencies_hz=frozenset({490_000, 518_000}),
    )
    assert tuple(decoder.decode(_frame())) == ()
    assert decoder._process is None


def test_builtin_decoder_frequency_contracts_are_disjoint_for_dsc_and_navtex():
    from core.radio.decoder_runtime import _builtin_decoder_frequencies

    navtex = _builtin_decoder_frequencies(("python", "scripts/radio_decoders/navtex_jsonl.py"))
    dsc = _builtin_decoder_frequencies(("dotnet", "SeaCommonsDscBridge.dll"))
    assert navtex == frozenset({490_000, 518_000})
    assert 2_187_500 in dsc
    assert navtex.isdisjoint(dsc)


def test_dsc_bridge_keeps_decoder_state_per_receiver_lineage():
    from pathlib import Path

    source = Path("third_party/radio/taosw_dsc/Bridge/Program.cs").read_text()
    assert "Dictionary<string, DecoderState>" in source
    assert 'physical_lineage' in source
    assert 'streamKey' in source


def test_pcm_quality_reports_silence_and_clipping_without_audio_persistence():
    from core.radio.decoder_runtime import _pcm_quality, RadioDecoderRuntime
    silence = _frame(b"\x00\x00" * 300)
    q = _pcm_quality(silence)
    assert q["valid_pcm"] and q["silent"] and not q["clipping"]
    loud = _frame(b"\x7f\xff" * 300)  # network-order full-scale positive
    q = _pcm_quality(loud)
    assert q["valid_pcm"] and q["clipping"] and not q["silent"]
    runtime = RadioDecoderRuntime(enabled=True, decoders=[], decoded_handler=lambda msg: {})
    runtime.ingest_frame(silence)
    status = runtime.status()
    assert status["audio_quality"]["sampled_frames"] == 1
    assert status["audio_quality"]["silent_frames"] == 1
    assert "payload" not in repr(status)


def test_pcm_quality_rejects_odd_length_and_supports_le():
    from core.radio.decoder_runtime import _pcm_quality
    from dataclasses import replace
    assert not _pcm_quality(_frame(b"\x01"))["valid_pcm"]
    frame = replace(_frame(b"\xff\x7f" * 200), encoding="openwebrx_pcm_s16le")
    assert _pcm_quality(frame)["clipping"]


def test_decoder_shards_preserve_receiver_frame_order():
    import time
    from dataclasses import replace
    from core.radio.decoder_runtime import RadioDecoderRuntime

    history = {}

    class RecordingDecoder:
        def decode(self, frame):
            history.setdefault(frame.receiver_id, []).append(frame.payload[0])
            time.sleep(0.001)
            return ()

    runtime = RadioDecoderRuntime(
        enabled=True, decoders=(RecordingDecoder(),),
        decoder_factory=lambda: (RecordingDecoder(),), worker_count=3,
        queue_size=64, decoded_handler=lambda msg: {},
    )
    assert runtime.status()["worker_count"] == 3
    from core.radio.decoder_runtime import _pcm_quality
    for i in range(20):
        for receiver in ("a", "b", "c"):
            frame = replace(_frame(), receiver_id=receiver,
                            physical_lineage=receiver, payload=bytes((i, 0)))
            assert runtime.submit_frame(frame)
    for q in runtime._queues:
        q.join()
    status = runtime.status()
    runtime.stop()
    assert status["frames"] == 60
    assert status["dropped"] == 0
    for receiver in ("a", "b", "c"):
        assert history[receiver] == list(range(20))


def test_same_lineage_maps_to_same_shard_even_when_receiver_id_changes():
    from dataclasses import replace
    from core.radio.decoder_runtime import RadioDecoderRuntime

    runtime = RadioDecoderRuntime(enabled=True, decoders=(),
                                  decoder_factory=lambda: (), worker_count=3,
                                  decoded_handler=lambda msg: {})
    a = _frame()
    b = replace(a, receiver_id="rx2")
    runtime.submit_frame(a)
    runtime.submit_frame(b)
    # All frames from one physical receiver must reach the same queue.
    assert max(q.qsize() for q in runtime._queues) <= 2
    assert sum(q.qsize() for q in runtime._queues) <= 2
    runtime.stop()


def test_dsc_bridge_buffers_incomplete_symbol_windows():
    from pathlib import Path
    source = Path('third_party/radio/taosw_dsc/Bridge/Program.cs').read_text()
    assert 'pendingSamples.AddRange(signal)' in source
    assert 'pendingSamples.Count / samplesPerSymbol * samplesPerSymbol' in source
    assert 'decoder.DecodeFSK(aligned, MarkHz, SpaceHz)' in source
    assert 'pendingSamples.RemoveRange(0, alignedCount)' in source


def test_decoder_rejects_invalid_audio_sequence_metadata():
    from dataclasses import replace
    import pytest
    assert replace(_frame(), sequence=0).sequence == 0
    assert replace(_frame(), sequence=0xFFFFFFFF).sequence == 0xFFFFFFFF
    with pytest.raises(ValueError, match="sequence"):
        replace(_frame(), sequence=-1)
    with pytest.raises(ValueError, match="sequence"):
        replace(_frame(), sequence=0x100000000)
    with pytest.raises(ValueError, match="session"):
        replace(_frame(), session_id="a" * 129)


def test_decoder_counts_persisted_separately_from_decoded_candidates():
    from core.radio.decoder_runtime import RadioDecoderRuntime
    class FakeDecoder:
        def decode(self, frame):
            return ({"kind": "dsc", "payload": {"category": "routine"}},)
    runtime = RadioDecoderRuntime(enabled=True, decoders=(FakeDecoder(),),
                                  decoded_handler=lambda msg: {"accepted": False})
    response = runtime.ingest_frame(_frame())
    assert response["decoded"] == 1 and response["persisted"] == 0
    assert runtime.status()["decoded"] == 1
    assert runtime.status()["accepted"] == 0
    assert runtime.status()["rejected"] == 1


def test_kiwi_audio_frame_includes_session_and_network_sequence(monkeypatch):
    from core.radio import decoder_runtime
    from core.radio.kiwisdr import KiwiSDRAdapter
    from tests.test_kiwisdr_adapter import FakeKiwiTransport, _descriptor, _snd_frame
    frames = []
    monkeypatch.setattr(decoder_runtime, "submit_ephemeral_frame", lambda frame: frames.append(frame) or True)
    transport = FakeKiwiTransport()
    adapter = KiwiSDRAdapter(_descriptor(), on_observation=lambda obs: None, transport=transport)
    adapter.start(); adapter.tune(2_187_500, "usb")
    transport.emit(b"MSG audio_init=0 audio_rate=12000")
    transport.emit(_snd_frame(sequence=101, audio=b"\x01\x02"))
    assert frames[0].session_id
    assert frames[0].sequence == 101


def test_openwebrx_sequence_detects_queue_drop(monkeypatch):
    from core.radio import decoder_runtime
    from core.radio.openwebrx import OpenWebRXAdapter
    from tests.test_openwebrx_adapter import FakeTransport, descriptor
    seen = []
    def fake_submit(frame):
        seen.append(frame)
        return len(seen) != 2
    monkeypatch.setattr(decoder_runtime, "submit_ephemeral_frame", fake_submit)
    transport = FakeTransport()
    adapter = OpenWebRXAdapter(descriptor(), on_observation=lambda obs: None, transport=transport)
    adapter.start()
    transport.on_message({"type":"config", "value":{"center_freq":2200000,
                          "samp_rate":200000, "audio_compression":"none"}})
    adapter.tune(2_187_500, "usb")
    for i in range(3): transport.on_message(b"\x02\x00\x00")
    assert len({x.session_id for x in seen}) == 1
    assert list(x.sequence for x in seen) == [1, 2, 3]
    assert [x.sequence for i,x in enumerate(seen) if i != 1] == [1, 3]


def test_process_decoder_reads_bounded_discontinuity_metrics(tmp_path):
    import sys
    from core.radio.decoder_runtime import JSONLProcessDecoder
    script = tmp_path / "decoder.py"
    script.write_text("import json,sys\nfor line in sys.stdin:\n d=json.loads(line); print(json.dumps({'messages':[], 'continuity_resets':1 if d['session_id'] == 'changed' else 0, 'state_evictions':0}),flush=True)\n")
    from dataclasses import replace
    decoder = JSONLProcessDecoder((sys.executable, str(script)), timeout_s=3)
    try:
        assert tuple(decoder.decode(replace(_frame(), session_id="changed", sequence=7))) == ()
        assert decoder.continuity_resets == 1
        assert decoder.state_evictions == 0
    finally:
        decoder.close()


def test_decoder_reports_bridge_error_counts_without_details(tmp_path):
    import sys
    from core.radio.decoder_runtime import JSONLProcessDecoder
    script = tmp_path / 'fake_bridge.py'
    script.write_text("import sys,json\nfor line in sys.stdin:\n print(json.dumps({'messages':[], 'bridge_errors':1}),flush=True)\n")
    decoder = JSONLProcessDecoder((sys.executable, str(script)), timeout_s=3)
    try:
        assert tuple(decoder.decode(_frame())) == ()
        assert decoder.bridge_errors == 1
    finally:
        decoder.close()
