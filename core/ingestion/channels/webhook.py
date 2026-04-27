# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generic JSON webhook handler — used by partner NGOs and API clients."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from core.ingestion.parsers.base import CoordinateExtractor
from core.ingestion.signal import DistressSignal

_extractor = CoordinateExtractor()


def handle_webhook(payload: dict[str, Any]) -> DistressSignal:
    """
    Parse a generic JSON webhook payload.

    Accepted payload shapes:
      A) {"lat": 35.1, "lon": 15.2, "text": "...", "source": "ngocall"}
      B) {"position": {"latitude": 35.1, "longitude": 15.2}, "message": "..."}
      C) Freeform {"body": "..."} — falls back to CoordinateExtractor
    """
    source_channel = str(payload.get("source_channel") or payload.get("source") or "webhook")
    source_id      = str(payload.get("source_id") or payload.get("sender") or uuid.uuid4())
    raw            = str(
        payload.get("text") or payload.get("message") or
        payload.get("body") or payload.get("raw_text") or ""
    )

    received_at = datetime.now(timezone.utc)
    if ts := payload.get("timestamp_utc") or payload.get("timestamp"):
        try:
            received_at = datetime.fromisoformat(str(ts))
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass

    # Try explicit coords first (shape A)
    lat: float | None = None
    lon: float | None = None
    confidence = 0.0
    method = "none"

    try:
        if "lat" in payload and "lon" in payload:
            lat = float(payload["lat"])
            lon = float(payload["lon"])
            confidence, method = 0.95, "webhook_explicit"
        elif "position" in payload:
            pos = payload["position"]
            lat = float(pos.get("latitude") or pos.get("lat"))
            lon = float(pos.get("longitude") or pos.get("lon"))
            confidence, method = 0.95, "webhook_explicit"
    except (ValueError, TypeError, AttributeError):
        lat = lon = None

    # Fall back to text extraction
    if lat is None and raw:
        lat, lon, confidence, method = _extractor.extract_coords(raw)

    persons   = int(payload["persons"]) if "persons" in payload else _extractor.extract_persons(raw)
    vessel_t  = payload.get("vessel_type") or _extractor.extract_vessel_type(raw)
    vessel_c  = payload.get("vessel_condition") or _extractor.extract_vessel_condition(raw)
    medical   = bool(payload.get("medical_emergency")) or _extractor.extract_medical(raw)
    children  = bool(payload.get("children_aboard")) or _extractor.extract_children(raw)

    return DistressSignal(
        signal_id=str(uuid.uuid4()),
        source_channel=source_channel,
        source_id=source_id,
        raw_text=raw or "[webhook payload]",
        lat=lat, lon=lon,
        timestamp_utc=received_at,
        persons=persons,
        vessel_type=vessel_t,
        vessel_condition=vessel_c,
        medical_emergency=medical,
        children_aboard=children,
        extraction_confidence=min(1.0, confidence),
        requires_human_review=confidence < 0.70,
        extraction_method=method,
        language_detected=_extractor.detect_language(raw) if raw else None,
    )
