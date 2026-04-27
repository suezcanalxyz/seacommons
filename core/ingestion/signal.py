# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical DistressSignal — produced by every channel parser."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class DistressSignal(BaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_channel: str                       # whatsapp | telegram | sms | twitter | api
    source_id: str                            # phone number, @handle, tweet_id, message_id
    source_name: Optional[str] = None        # display name if known
    raw_text: str                             # original message, unmodified
    lat: Optional[float] = None              # None if extraction failed
    lon: Optional[float] = None              # None if extraction failed
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_time_utc: Optional[datetime] = None  # when the incident happened if stated
    persons: Optional[int] = None            # number of people in distress
    vessel_type: Optional[str] = None        # rubber_boat | wooden_boat | sailboat | unknown
    vessel_condition: Optional[str] = None   # sinking | taking_water | engine_failure | unknown
    medical_emergency: bool = False
    children_aboard: bool = False
    extraction_confidence: float = 0.0       # 0.0–1.0
    requires_human_review: bool = True       # True if confidence < 0.70
    extraction_method: str = "regex"         # regex | llm | manual | shared_location
    language_detected: Optional[str] = None  # iso 639-1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DistressSignal":
        """Deserialise from a plain dict (e.g., from JSON store)."""
        return cls.model_validate(data)

    def to_alert_dict(self) -> dict[str, Any]:
        """Convert to the format expected by POST /api/v1/alert."""
        return {
            "alert_id": self.signal_id,
            "source": f"{self.source_channel}:{self.source_id}",
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "lat": self.lat,
            "lon": self.lon,
            "classification": "distress_signal",
            "confidence": self.extraction_confidence,
            "metadata": {
                "persons": self.persons,
                "vessel_type": self.vessel_type,
                "vessel_condition": self.vessel_condition,
                "medical_emergency": self.medical_emergency,
                "children_aboard": self.children_aboard,
                "raw_text": self.raw_text,
                "requires_human_review": self.requires_human_review,
            },
        }


if __name__ == "__main__":
    sig = DistressSignal(
        source_channel="whatsapp",
        source_id="+39000000000",
        raw_text="45 persone su gommone, acqua dentro",
        lat=35.5, lon=12.6,
        persons=45,
        vessel_type="rubber_boat",
        vessel_condition="taking_water",
        extraction_confidence=0.85,
        requires_human_review=False,
        extraction_method="regex",
    )
    data = sig.model_dump(mode="json")
    sig2 = DistressSignal.from_dict(data)
    assert sig2.signal_id == sig.signal_id
    assert sig2.persons == 45
    alert = sig.to_alert_dict()
    assert alert["classification"] == "distress_signal"
    print("DistressSignal self-test OK:", sig.signal_id[:8])
