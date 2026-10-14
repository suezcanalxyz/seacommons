from __future__ import annotations

from array import array
from dataclasses import dataclass
import sys
import math

_ALLOWED = {"kiwi_snd_raw", "openwebrx_pcm_s16le", "pcm_s16le"}


@dataclass(frozen=True)
class NormalizedPCM:
    payload: bytes
    sample_rate_hz: int
    encoding: str = "pcm_s16le"


def _decode_s16(payload: bytes, *, byteorder: str) -> array:
    if not payload or len(payload) % 2:
        raise ValueError("PCM16 payload must be non-empty and 16-bit aligned")
    values = array("h")
    values.frombytes(payload)
    if values.itemsize != 2:
        raise RuntimeError("unexpected host short size")
    if byteorder not in {"little", "big"}:
        raise ValueError("unsupported PCM16 byte order")
    if byteorder != sys.byteorder:
        values.byteswap()
    return values


def _encode_s16le(values: array) -> bytes:
    encoded = array("h", values)
    if sys.byteorder != "little":
        encoded.byteswap()
    return encoded.tobytes()


# Windowed-sinc low-pass for the OpenWebRX HD PCM (48 kHz) -> decoder
# (12 kHz) conversion. Fixed coefficients avoid allocations per frame; only
# decimated output samples are convolved. This does not retain raw audio.
_FIR_TAPS = 41
_FIR_CUTOFF_HZ = 3_000


def _fir_48k_to_12k_coefficients() -> tuple[float, ...]:
    centre = (_FIR_TAPS - 1) / 2
    cutoff = _FIR_CUTOFF_HZ / 48_000
    coefficients = []
    for k in range(_FIR_TAPS):
        x = k - centre
        sinc = 2 * cutoff if x == 0 else math.sin(2 * math.pi * cutoff * x) / (math.pi * x)
        window = 0.54 - 0.46 * math.cos(2 * math.pi * k / (_FIR_TAPS - 1))
        coefficients.append(sinc * window)
    normalization = sum(coefficients)
    return tuple(value / normalization for value in coefficients)


_FIR_48K_COEFFICIENTS = _fir_48k_to_12k_coefficients()


def _downsample_48k_to_12k(samples: array) -> array:
    """Anti-aliased 4:1 decimation for OpenWebRX HD audio.

    Edge samples are clamped instead of zero-padded; this is still stateless
    on purpose, so decoder processes never retain audio after a stream gap.
    The DSC 1615/1785 Hz mark/space pair lies below the 3 kHz cutoff.
    """
    result = array("h")
    size = len(samples)
    centre = _FIR_TAPS // 2
    coefficients = _FIR_48K_COEFFICIENTS
    for output_index in range(max(1, round(size / 4))):
        position = output_index * 4
        value = 0.0
        for tap, weight in enumerate(coefficients):
            source = max(0, min(size - 1, position + tap - centre))
            value += samples[source] * weight
        result.append(max(-32768, min(32767, round(value))))
    return result


def _resample_linear(samples: array, in_rate: int, out_rate: int) -> array:
    if in_rate == out_rate:
        return samples
    if in_rate <= 0 or out_rate <= 0:
        raise ValueError("sample rates must be positive")
    if in_rate == 48_000 and out_rate == 12_000:
        return _downsample_48k_to_12k(samples)
    out_len = max(1, round(len(samples) * out_rate / in_rate))
    result = array("h")
    scale = in_rate / out_rate
    for index in range(out_len):
        pos = index * scale
        left = min(int(pos), len(samples) - 1)
        right = min(left + 1, len(samples) - 1)
        frac = pos - left
        value = round(samples[left] + (samples[right] - samples[left]) * frac)
        result.append(max(-32768, min(32767, value)))
    return result


def normalize_pcm16le(payload: bytes, *, encoding: str, sample_rate_hz: int, target_rate_hz: int = 12_000) -> NormalizedPCM:
    normalized_encoding = str(encoding).strip().lower()
    if normalized_encoding not in _ALLOWED:
        raise ValueError("unsupported ephemeral audio encoding")
    # KiwiSDR's ordinary non-camping mono SND stream is network-order
    # signed 16-bit PCM. OpenWebRX and our internal normalized form are LE.
    byteorder = "big" if normalized_encoding == "kiwi_snd_raw" else "little"
    values = _decode_s16(payload, byteorder=byteorder)
    normalized = _resample_linear(values, int(sample_rate_hz), int(target_rate_hz))
    return NormalizedPCM(payload=_encode_s16le(normalized), sample_rate_hz=int(target_rate_hz))
