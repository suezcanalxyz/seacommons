from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


EventKind = Literal["position_fix", "vessel_track", "distress_signal", "sensor_observation", "target_contact"]


class SourceRef(BaseModel):
    protocol: str
    adapter: str
    vessel_id: Optional[str] = None
    device_id: Optional[str] = None
    transport: Optional[str] = None
    raw_sentence: Optional[str] = None


class NormalizedEvent(BaseModel):
    event_type: EventKind
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: SourceRef
    lat: Optional[float] = None
    lon: Optional[float] = None
    course: Optional[float] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    altitude: Optional[float] = None
    status: Optional[str] = None
    confidence: Optional[float] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
