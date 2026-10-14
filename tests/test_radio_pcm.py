from __future__ import annotations

from array import array
import struct


def test_kiwi_raw_big_endian_pcm_is_normalized_to_12khz_s16le():
    from core.radio.pcm import normalize_pcm16le

    values = [0, 1000, -1000, 32767, -32768]
    payload = struct.pack(">5h", *values)
    out = normalize_pcm16le(payload, encoding="kiwi_snd_raw", sample_rate_hz=12_000)
    assert out.sample_rate_hz == 12_000
    assert out.encoding == "pcm_s16le"
    assert out.payload == struct.pack("<5h", *values)


def test_48khz_pcm_is_downsampled_to_12khz_bounded():
    from core.radio.pcm import normalize_pcm16le

    samples = array("h", range(0, 400))
    out = normalize_pcm16le(samples.tobytes(), encoding="openwebrx_pcm_s16le", sample_rate_hz=48_000)
    assert out.sample_rate_hz == 12_000
    assert len(out.payload) == 200


def test_unknown_or_misaligned_audio_fails_closed():
    import pytest
    from core.radio.pcm import normalize_pcm16le

    with pytest.raises(ValueError):
        normalize_pcm16le(b"abc", encoding="openwebrx_audio", sample_rate_hz=12_000)
    with pytest.raises(ValueError):
        normalize_pcm16le(b"abc", encoding="kiwi_snd_raw", sample_rate_hz=12_000)


def _sinusoid_pcm(frequency: float, rate: int, duration_s: float = 0.4) -> bytes:
    from math import sin, pi
    return struct.pack(f"<{round(rate * duration_s)}h", *(
        round(12_000 * sin(2 * pi * frequency * n / rate))
        for n in range(round(rate * duration_s))
    ))


def _rms_pcm(payload: bytes, *, skip: int = 200) -> float:
    values = array("h")
    values.frombytes(payload)
    data = values[skip:-skip] if len(values) > 2 * skip else values
    return (sum(value * value for value in data) / len(data)) ** 0.5


def test_48khz_to_12khz_antialias_rejects_out_of_band_tones():
    from core.radio.pcm import normalize_pcm16le

    def measure(frequency):
        payload = _sinusoid_pcm(frequency, 48_000)
        converted = normalize_pcm16le(payload, encoding="openwebrx_pcm_s16le", sample_rate_hz=48_000)
        return _rms_pcm(converted.payload)

    lower = measure(1615)
    upper = measure(1785)
    high = measure(10_500)  # Would alias to 1500 Hz without anti-alias filtering.
    assert 6500 < lower < 9500
    assert 6500 < upper < 9500
    assert high < lower * 0.05


def test_48khz_pcm_stays_bounded_on_short_frames():
    from core.radio.pcm import normalize_pcm16le
    for values in ([50], [100, -100], [100] * 9):
        payload = struct.pack(f"<{len(values)}h", *values)
        converted = normalize_pcm16le(payload, encoding="openwebrx_pcm_s16le", sample_rate_hz=48000)
        assert len(converted.payload) == max(1, round(len(values)/4)) * 2
        assert max(abs(x) for x in struct.unpack(f"<{len(converted.payload)//2}h", converted.payload)) <= 100
