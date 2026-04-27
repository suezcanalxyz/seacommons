# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ingestion API routes — receive distress signals from all channels."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.ingestion import router as ingest_router
from core.ingestion.signal import DistressSignal

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


# ── Request / Response models ──────────────────────────────────────────────────

class TwilioForm(BaseModel):
    Body: str = ""
    From: str = "unknown"
    MessageSid: str = ""
    Latitude: str = ""
    Longitude: str = ""


class WebhookPayload(BaseModel):
    source_channel: str = "webhook"
    source_id: str = ""
    text: str = ""
    lat: float | None = None
    lon: float | None = None
    persons: int | None = None
    vessel_type: str | None = None
    vessel_condition: str | None = None
    medical_emergency: bool = False
    children_aboard: bool = False
    timestamp_utc: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/twilio/whatsapp", response_model=dict)
async def twilio_whatsapp(request: Request) -> dict:
    """Twilio inbound WhatsApp webhook."""
    form = await request.form()
    form_dict = dict(form)
    sig = ingest_router.ingest_twilio_whatsapp(form_dict)
    return _sig_summary(sig)


@router.post("/twilio/sms", response_model=dict)
async def twilio_sms(request: Request) -> dict:
    """Twilio inbound SMS webhook."""
    form = await request.form()
    form_dict = dict(form)
    sig = ingest_router.ingest_twilio_sms(form_dict)
    return _sig_summary(sig)


@router.post("/telegram", response_model=dict)
async def telegram_update(request: Request) -> dict:
    """Telegram Bot API webhook endpoint."""
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    sig = ingest_router.ingest_telegram(payload)
    if sig is None:
        return {"status": "ignored", "reason": "no parsable message"}
    return _sig_summary(sig)


@router.post("/webhook", response_model=dict)
async def generic_webhook(payload: WebhookPayload) -> dict:
    """Generic JSON webhook for partner NGOs and API clients."""
    sig = ingest_router.ingest_webhook(payload.model_dump(exclude_none=True))
    return _sig_summary(sig)


@router.get("/signals", response_model=list[dict])
async def list_signals(limit: int = 100) -> list[dict]:
    """Return the most recent ingested distress signals."""
    signals = ingest_router.load_recent(limit=min(limit, 500))
    return [s.model_dump(mode="json") for s in signals]


@router.get("/signals/{signal_id}", response_model=dict)
async def get_signal(signal_id: str) -> dict:
    """Return a single signal by ID (searches recent store)."""
    signals = ingest_router.load_recent(limit=500)
    for sig in signals:
        if sig.signal_id == signal_id:
            return sig.model_dump(mode="json")
    raise HTTPException(status_code=404, detail="Signal not found")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sig_summary(sig: DistressSignal) -> dict:
    return {
        "status": "ok",
        "signal_id": sig.signal_id,
        "source_channel": sig.source_channel,
        "lat": sig.lat,
        "lon": sig.lon,
        "extraction_confidence": sig.extraction_confidence,
        "requires_human_review": sig.requires_human_review,
        "urgency": "IMMEDIATE" if sig.requires_human_review else "ROUTINE",
    }
