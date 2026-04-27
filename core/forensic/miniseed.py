# SPDX-License-Identifier: AGPL-3.0-or-later
"""MiniSEED packaging for waveform data in forensic packets."""
from __future__ import annotations
import base64
import io


class MiniSEEDPackager:
    @staticmethod
    def pack(trace: object, event_id: str) -> bytes:
        """Convert ObsPy Trace to MiniSEED bytes."""
        try:
            buf = io.BytesIO()
            trace.write(buf, format="MSEED")  # type: ignore[attr-defined]
            return buf.getvalue()
        except Exception as exc:
            raise RuntimeError(f"MiniSEED pack failed: {exc}") from exc

    @staticmethod
    def verify(miniseed_bytes: bytes) -> object:
        """Read MiniSEED bytes back to ObsPy Stream."""
        try:
            from obspy import read  # type: ignore[import]
            buf = io.BytesIO(miniseed_bytes)
            return read(buf, format="MSEED")
        except ImportError:
            raise RuntimeError("obspy not installed")

    @staticmethod
    def to_base64(miniseed_bytes: bytes) -> str:
        return base64.b64encode(miniseed_bytes).decode()

    @staticmethod
    def from_base64(b64: str) -> bytes:
        return base64.b64decode(b64)


if __name__ == "__main__":
    print("MiniSEEDPackager OK (obspy optional)")
    rt = MiniSEEDPackager.from_base64(MiniSEEDPackager.to_base64(b"test"))
    print("  round-trip:", rt == b"test")
