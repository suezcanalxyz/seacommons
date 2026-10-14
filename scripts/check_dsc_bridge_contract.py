#!/usr/bin/env python3
"""Offline DSC JSONL bridge release gate. No RF transmissions or audio storage."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import struct
import subprocess
import sys


def envelope(samples: bytes, *, index: int, lineage: str = "test-rx", sequence: int | None = None,
             session: str = "test-session", offset_ms: float = 0) -> dict[str, object]:
    return {
        "encoding": "pcm_s16le", "frequency_hz": 2_187_500,
        "sample_rate_hz": 12_000, "physical_lineage": lineage,
        "receiver_id": lineage, "session_id": session,
        "sequence": sequence,
        "observed_at": (datetime(2026, 10, 14, tzinfo=timezone.utc)
                        + timedelta(milliseconds=offset_ms)).isoformat(),
        "payload_b64": base64.b64encode(samples).decode("ascii"),
    }


def _routine_call_packets(*, valid_ecc: bool, preamble_bits: int = 0,
                          inverted_polarity: bool = False) -> list[dict[str, object]]:
    """Generate one synthetic NON-DISTRESS routine DSC call in memory.

    All-ships / routine at 100 baud, with the 7 DX / 8 RX phasing groups,
    7-bit payload plus 3-bit parity, time-diverse repeat, and vertical XOR
    ECC. No RF transmission, logging of PCM, or operational ingestion.
    """
    # The two format specifiers are 116 (all-ships), category=100 (routine),
    # with a fictitious test identity and EOS=127 (other calls).
    message = [116, 116, 100, 12, 34, 56, 78, 90, 109, 126,
               0, 0, 0, 0, 0, 0, 127]
    ecc = 0
    for code in message[1:]:
        ecc ^= code
    message.append(ecc if valid_ecc else ecc ^ 1)
    dx = [125] * 7 + message + [0] * 45
    rx = list(range(111, 103, -1)) + [0, 0] + message + [0] * 43
    characters = []
    for index in range(max(len(dx), len(rx))):
        if index < len(dx):
            characters.append(dx[index])
        if index < len(rx):
            characters.append(rx[index])
    bits = [1, 0] * (preamble_bits // 2)
    for character in characters:
        bits.extend((character >> shift) & 1 for shift in range(7))
        parity = 7 - character.bit_count()
        bits.extend((parity >> shift) & 1 for shift in (2, 1, 0))

    # Continuous-phase, two-tone FSK; 12 kHz PCM and exactly 120 samples/bit.
    phase = 0.0
    samples = []
    for bit in bits:
        step = 2 * math.pi * (1785 if bit else 1615) / 12_000 if inverted_polarity \
            else 2 * math.pi * (1615 if bit else 1785) / 12_000
        for _ in range(120):
            samples.append(int(10_000 * math.sin(phase)))
            phase = (phase + step) % (2 * math.pi)

    result: list[dict[str, object]] = []
    sample_index = 0
    widths = (240, 360, 480, 720, 960, 1024)
    stream_id = "synthetic-routine-valid" if valid_ecc else "synthetic-routine-invalid"
    if inverted_polarity:
        stream_id += "-inverted"
    while sample_index < len(samples):
        size = min(widths[len(result) % len(widths)], len(samples) - sample_index)
        pcm = struct.pack(f"<{size}h", *samples[sample_index:sample_index+size])
        result.append(envelope(
            pcm, index=len(result), lineage=stream_id, session=stream_id,
            sequence=len(result), offset_ms=1000 * sample_index / 12_000,
        ))
        sample_index += size
    return result


def check_valid_dsc_routine_audio(dll: Path) -> None:
    """Positive end-to-end release gate. Never forward this fixture to LIVE."""
    for valid_ecc, preamble_bits, inverted_polarity in (
        (True, 0, False), (True, 200, False), (True, 0, True),
        (False, 0, False), (False, 0, True),
    ):
        packets = _routine_call_packets(valid_ecc=valid_ecc, preamble_bits=preamble_bits,
                                         inverted_polarity=inverted_polarity)
        result = subprocess.run(
            ["dotnet", str(dll.resolve())],
            input="\n".join(json.dumps(packet) for packet in packets) + "\n",
            capture_output=True, text=True, timeout=40, check=True,
        )
        output = [json.loads(line) for line in result.stdout.splitlines()]
        assert len(output) == len(packets), "positive DSC JSONL replies missing"
        assert all(item.get("bridge_errors") == 0 for item in output), "DSC bridge processing error"
        assert all(item.get("continuity_resets") == 0 for item in output), "synthetic stream unexpectedly reset"
        messages = [msg for item in output for msg in item.get("messages", ())]
        if valid_ecc:
            assert len(messages) == 1, "valid routine DSC audio not decoded exactly once"
            assert messages[0]["kind"] == "dsc"
            payload = messages[0]["payload"]
            assert payload["status"] == "OK"
            assert payload["category"] == "routine"
            assert payload["format"] == "AllShipsCall"
        else:
            assert not messages, "corrupt-ECC audio emitted as a valid DSC message"
    print("Valid DSC routine decoded in both FSK polarities; invalid ECC rejected (offline)")


def check(dll: Path) -> None:
    # Synthetic 100-baud mark/space tones deliberately contain no DSC format,
    # time-diversity or ECC. They are *not* a distress signal.
    samples = [round(9000 * math.sin(2 * math.pi *
               (1615 if int(i / 120) % 2 == 0 else 1785) * i / 12000))
               for i in range(12000)]
    stream = struct.pack(f"<{len(samples)}h", *samples)
    chunks: list[dict[str, object]] = []
    sample_index = 0
    widths = (83, 157, 1, 119, 240, 271, 449)
    while sample_index < len(samples):
        size = min(widths[len(chunks) % len(widths)], len(samples) - sample_index)
        chunks.append(envelope(stream[sample_index*2:(sample_index+size)*2],
                      index=len(chunks), sequence=len(chunks),
                      offset_ms=1000 * sample_index / 12000))
        sample_index += size

    # A gap in an otherwise continuous stream and a later reconnect both
    # must reset the C# GMDSS symbol state, not silently concatenate it.
    zeros = b"\x00\x00" * 180
    start_index = len(chunks)
    cases = [
        envelope(zeros, index=start_index, sequence=start_index+2, offset_ms=1000),
        envelope(zeros, index=start_index+1, sequence=start_index+3,
                 session="new-session", offset_ms=1015),
    ]
    # Bound C# state by presenting 70 different synthetic streams.
    cases += [envelope(zeros, index=i, sequence=0, lineage=f"self-test-{i}", offset_ms=2000)
              for i in range(70)]
    malformed = envelope(zeros, index=0, lineage="bad-frame", offset_ms=2000)
    malformed["payload_b64"] = "invalid base64!!!"
    cases.append(malformed)
    packets = chunks + cases
    result = subprocess.run(
        ["dotnet", str(dll.resolve())],
        input="\n".join(json.dumps(p) for p in packets) + "\n",
        capture_output=True, text=True, timeout=40, check=True,
    )
    answers = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(answers) == len(packets), "JSONL response count changed"
    assert all(row.get("messages") == [] for row in answers), "unexpected decoded message"
    assert all(row.get("bridge_errors") == 0 for row in answers[:-1]), "valid PCM failed"
    assert answers[-1].get("bridge_errors") == 1, "malformed PCM not diagnosed"
    assert all(row.get("continuity_resets") == 0 for row in answers[:len(chunks)]), "symbol boundary reset"
    assert answers[len(chunks)].get("continuity_resets") == 1, "sequence gap not detected"
    assert answers[len(chunks)+1].get("continuity_resets") == 1, "session reconnect not detected"
    assert sum(row.get("state_evictions", 0) for row in answers) >= 1, "stream state unbounded"
    print(f"DSC bridge offline contract passed ({len(packets)} JSONL responses, no transmissions)")


if __name__ == "__main__":
    assert len(sys.argv) == 2, "usage: check_dsc_bridge_contract.py path/to/SeaCommonsDscBridge.dll"
    check(Path(sys.argv[1]))
    check_valid_dsc_routine_audio(Path(sys.argv[1]))
