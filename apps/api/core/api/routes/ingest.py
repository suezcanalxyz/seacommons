# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ingestion API routes — receive distress signals from all channels."""
from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from core.config import config
from core.connectors.service import active_whatsapp_connector, mark_seen, public_connector
from core.db.session import session_scope
from core.domain.live_contracts import PublicationStatus
from core.ingestion import router as ingest_router
from core.ingestion.signal import DistressSignal
from core.security import authenticate

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
    publication_status: PublicationStatus = PublicationStatus.PRIVATE


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/twilio/whatsapp", response_model=dict)
async def twilio_whatsapp(request: Request) -> dict:
    """Twilio inbound WhatsApp webhook."""
    form = await request.form()
    form_dict = dict(form)
    _verify_twilio(request, form_dict)
    sig = ingest_router.ingest_twilio_whatsapp(form_dict)
    return _sig_summary(sig)


@router.get("/meta/whatsapp", response_class=PlainTextResponse)
async def meta_whatsapp_verify(request: Request) -> PlainTextResponse:
    """Meta webhook subscription challenge."""
    mode = request.query_params.get("hub.mode", "")
    supplied = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")
    expected = config.META_WEBHOOK_VERIFY_TOKEN
    if not expected:
        raise HTTPException(status_code=503, detail="Meta webhook is not configured")
    if mode != "subscribe" or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Invalid Meta verification token")
    return PlainTextResponse(challenge)


@router.post("/meta/whatsapp", response_model=dict)
async def meta_whatsapp(request: Request) -> dict:
    """Receive signed WhatsApp Cloud API messages for partner-owned numbers."""
    raw = await _limited_body(request)
    secret = config.META_APP_SECRET
    if not secret:
        raise HTTPException(status_code=503, detail="Meta webhook is not configured")
    supplied = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid Meta webhook signature")
    try:
        import json
        payload: dict[str, Any] = json.loads(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    if payload.get("object") != "whatsapp_business_account":
        return {"status": "ignored", "reason": "unsupported object", "accepted": 0}

    accepted: list[str] = []
    unknown_channels: set[str] = set()
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            phone_number_id = str((value.get("metadata") or {}).get("phone_number_id") or "")
            if not phone_number_id or not value.get("messages"):
                continue
            with session_scope() as db:
                row = active_whatsapp_connector(db, phone_number_id)
                if row is None:
                    unknown_channels.add(phone_number_id or "missing")
                    continue
                connector = public_connector(row)
                mark_seen(row)
            signals = ingest_router.ingest_meta_whatsapp(value, connector)
            accepted.extend(signal.signal_id for signal in signals)
    return {
        "status": "accepted" if accepted else "ignored",
        "accepted": len(accepted),
        "signal_ids": accepted,
        "unknown_channels": sorted(unknown_channels),
    }


@router.post("/twilio/sms", response_model=dict)
async def twilio_sms(request: Request) -> dict:
    """Twilio inbound SMS webhook."""
    form = await request.form()
    form_dict = dict(form)
    _verify_twilio(request, form_dict)
    sig = ingest_router.ingest_twilio_sms(form_dict)
    return _sig_summary(sig)


@router.post("/telegram", response_model=dict)
async def telegram_update(request: Request) -> dict:
    """Telegram Bot API webhook endpoint."""
    expected = config.TELEGRAM_WEBHOOK_SECRET
    supplied = request.headers.get("x-telegram-bot-api-secret-token", "")
    if expected and not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")
    if config.RUNTIME_PROFILE.lower() in {"production", "prod"} and not expected:
        raise HTTPException(status_code=503, detail="Telegram webhook is not configured securely")
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    command = _handle_telegram_command(payload)
    if command is not None:
        return command
    sig = ingest_router.ingest_telegram(payload)
    if sig is None:
        return {"status": "ignored", "reason": "no parsable message"}
    return _sig_summary(sig)


@router.post("/webhook", response_model=dict)
async def generic_webhook(request: Request) -> dict:
    """Generic JSON webhook for partner NGOs and API clients."""
    raw = await _limited_body(request)
    expected = config.PARTNER_WEBHOOK_SECRET
    supplied = request.headers.get("x-seacommons-signature", "")
    digest = "sha256=" + hmac.new(expected.encode(), raw, hashlib.sha256).hexdigest() if expected else ""
    if expected and not hmac.compare_digest(supplied, digest):
        raise HTTPException(status_code=401, detail="Invalid partner webhook signature")
    if config.RUNTIME_PROFILE.lower() in {"production", "prod"} and not expected:
        raise HTTPException(status_code=503, detail="Partner webhook is not configured securely")
    try:
        payload = WebhookPayload.model_validate_json(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc
    sig = ingest_router.ingest_webhook(payload.model_dump(exclude_none=True))
    return _sig_summary(sig)


def _principal_organization(request: Request) -> str | None:
    principal = authenticate(request)
    if principal is None or "administrator" in principal.roles:
        return None
    value: Any = principal.claims
    for part in config.OIDC_ORGANIZATION_CLAIM.split("."):
        if not isinstance(value, dict):
            return ""
        value = value.get(part)
    return str(value or "")


@router.get("/signals", response_model=list[dict])
async def list_signals(request: Request, limit: int = 100) -> list[dict]:
    """Return the most recent ingested distress signals."""
    signals = ingest_router.load_recent(
        limit=min(limit, 500), organization_id=_principal_organization(request)
    )
    return [s.model_dump(mode="json") for s in signals]


@router.get("/signals/{signal_id}", response_model=dict)
async def get_signal(signal_id: str, request: Request) -> dict:
    """Return a single signal by ID (searches recent store)."""
    signals = ingest_router.load_recent(
        limit=500, organization_id=_principal_organization(request)
    )
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


async def _limited_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and int(declared) > config.MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Webhook body too large")
    body = await request.body()
    if len(body) > config.MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Webhook body too large")
    return body


def _verify_twilio(request: Request, form: dict[str, Any]) -> None:
    """Verify Twilio's HMAC-SHA1 signature without requiring its SDK."""
    token = config.TWILIO_AUTH_TOKEN
    if not token:
        if config.RUNTIME_PROFILE.lower() in {"production", "prod"}:
            raise HTTPException(status_code=503, detail="Twilio webhook is not configured securely")
        return
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    url = f"{forwarded_proto}://{forwarded_host}{request.url.path}"
    if request.url.query:
        url += "?" + request.url.query
    canonical = url + "".join(k + str(form[k]) for k in sorted(form))
    expected = base64.b64encode(hmac.new(token.encode(), canonical.encode(), hashlib.sha1).digest()).decode()
    supplied = request.headers.get("x-twilio-signature", "")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid Twilio webhook signature")


def _handle_telegram_command(payload: dict[str, Any]) -> dict | None:
    """Allow the configured operations chat to update cases through the bot."""
    import re
    import uuid
    from core.audit import record
    from core.db.models import CaseDB, CaseTimelineDB
    from core.db.session import session_scope

    message = payload.get("message") or {}
    text = str(message.get("text") or "").strip()
    if not text.startswith(("/case ", "/status ")):
        return None
    chat_id = str((message.get("chat") or {}).get("id", ""))
    if not config.TELEGRAM_OPERATIONS_CHAT_ID or not hmac.compare_digest(chat_id, config.TELEGRAM_OPERATIONS_CHAT_ID):
        raise HTTPException(status_code=403, detail="Telegram chat is not authorised for operations")
    actor = f"telegram:{chat_id}"
    note = re.fullmatch(r"/case\s+([0-9a-fA-F-]{8,36})\s+(.+)", text, re.DOTALL)
    status = re.fullmatch(r"/status\s+([0-9a-fA-F-]{8,36})\s+(open|triage|active|monitoring|resolved|closed)", text)
    match = note or status
    if not match:
        raise HTTPException(status_code=422, detail="Use /case <id> <note> or /status <id> <status>")
    case_ref = match.group(1).lower()
    with session_scope() as db:
        rows = db.query(CaseDB).filter(CaseDB.case_id.like(f"{case_ref}%")).limit(2).all()
        if len(rows) != 1:
            raise HTTPException(status_code=404, detail="Case prefix not found or ambiguous")
        case = rows[0]
        if note:
            body = note.group(2).strip()
            case_event = "note"
            action = "case.telegram_note"
        else:
            case.status = status.group(2)
            body = f"Status changed to {case.status}"
            case_event = "updated"
            action = "case.telegram_status"
        db.add(CaseTimelineDB(entry_id=str(uuid.uuid4()), case_id=case.case_id,
                              event_type=case_event, actor=actor, body=body, data={"channel": "telegram"}))
        record(db, actor=actor, action=action, resource_type="case", resource_id=case.case_id)
        return {"status": "ok", "case_id": case.case_id, "action": action}
