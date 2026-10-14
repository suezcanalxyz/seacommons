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
