#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import select
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BIN = ROOT / "third_party/radio/radiom_navtex/decoder/bin/navtex-decoder"
NAVTEX_BIN = Path(os.environ.get("SEACOMMONS_NAVTEX_BIN", DEFAULT_BIN))
NAVTEX_FREQS = {490_000, 518_000}
BLOCK_RE = re.compile(r"ZCZC\s+[A-Z][A-Z]\d{2}.*?NNNN", re.S | re.I)
MAX_BUFFER = 65_536

proc: subprocess.Popen[bytes] | None = None
text_buffer = ""


def ensure_proc() -> subprocess.Popen[bytes]:
    global proc
    if proc is not None and proc.poll() is None:
        return proc
    if not NAVTEX_BIN.is_file():
        raise FileNotFoundError(str(NAVTEX_BIN))
    proc = subprocess.Popen(
        [str(NAVTEX_BIN), "--mode=navtex"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        bufsize=0, close_fds=True,
    )
    return proc


def drain_output(process: subprocess.Popen[bytes]) -> list[dict[str, object]]:
    global text_buffer
    assert process.stdout is not None
    while True:
        ready, _, _ = select.select([process.stdout], [], [], 0)
        if not ready:
            break
        chunk = os.read(process.stdout.fileno(), 4096)
        if not chunk:
            break
        text_buffer = (text_buffer + chunk.decode("latin-1", errors="ignore"))[-MAX_BUFFER:]
    messages: list[dict[str, object]] = []
    while True:
        match = BLOCK_RE.search(text_buffer)
        if match is None:
            break
        block = match.group(0).replace("\r", "").strip()
        text_buffer = text_buffer[match.end():]
        messages.append({"kind": "navtex", "payload": block})
    return messages[:16]


def handle(envelope: dict[str, object]) -> list[dict[str, object]]:
    frequency = int(envelope.get("frequency_hz") or 0)
    if frequency not in NAVTEX_FREQS or envelope.get("encoding") != "pcm_s16le":
        return []
    payload = base64.b64decode(str(envelope.get("payload_b64") or ""), validate=True)
    if not payload or len(payload) % 2:
        return []
    process = ensure_proc()
    assert process.stdin is not None
    process.stdin.write(payload)
    process.stdin.flush()
    return drain_output(process)


for raw in sys.stdin:
    try:
        parsed = json.loads(raw)
        messages = handle(parsed) if isinstance(parsed, dict) else []
    except Exception:
        messages = []
    print(json.dumps({"messages": messages}, separators=(",", ":")), flush=True)
