from __future__ import annotations

from array import array
from dataclasses import dataclass

_ALLOWED = {"kiwi_snd_raw", "openwebrx_pcm_s16le", "pcm_s16le"}


@dataclass(frozen=True)
class NormalizedPCM:
    payload: bytes
    sample_rate_hz: int
    encoding: str = "pcm_s16le"


def _decode_s16le(payload: bytes) -> array:
    if not payload or len(payload) % 2:
        raise ValueError("PCM16 payload must be non-empty and 16-bit aligned")
    values = array("h")
    values.frombytes(payload)
    if values.itemsize != 2:
        raise RuntimeError("unexpected host short size")
    return values


def _resample_linear(samples: array, in_rate: int, out_rate: int) -> array:
    if in_rate == out_rate:
        return samples
    if in_rate <= 0 or out_rate <= 0:
        raise ValueError("sample rates must be positive")
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
    if str(encoding).strip().lower() not in _ALLOWED:
        raise ValueError("unsupported ephemeral audio encoding")
    values = _decode_s16le(payload)
    normalized = _resample_linear(values, int(sample_rate_hz), int(target_rate_hz))
    return NormalizedPCM(payload=normalized.tobytes(), sample_rate_hz=int(target_rate_hz))
