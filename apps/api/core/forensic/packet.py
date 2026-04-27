# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical forensic packet schema — all signed events use this model."""
from __future__ import annotations
import uuid
from typing import Any
from pydantic import BaseModel, Field


class ForensicPacket(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_utc: str
    classification: str
    confidence: float
    position: dict[str, Any]          # {lat, lon, alt, source}
    vessel_id: str = ""
    contributing_sensors: list[str] = []
    sensor_data: dict[str, Any] = {}
    drift_result: dict[str, Any] = {}
    waveform_miniseed_b64: str = ""
    rinex_dtec_b64: str = ""
    acled_events: list[dict] = []
    emsc_events: list[dict] = []
    public_key: str = ""
    hash_blake3: str = ""
    signature_ed25519: str = ""


if __name__ == "__main__":
    from datetime import datetime, timezone
    pkt = ForensicPacket(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        classification="test",
        confidence=0.5,
        position={"lat": 35.5, "lon": 14.0, "alt": 0, "source": "manual"},
    )
    print("ForensicPacket OK:", pkt.event_id)
