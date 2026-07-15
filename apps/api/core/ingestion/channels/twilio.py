# SPDX-License-Identifier: AGPL-3.0-or-later
"""Twilio channel handler — WhatsApp + SMS inbound webhooks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.ingestion.parsers.whatsapp import WhatsAppParser
from core.ingestion.parsers.sms import SMSParser
from core.ingestion.signal import DistressSignal


_whatsapp_parser = WhatsAppParser()
_sms_parser = SMSParser()


def handle_twilio_whatsapp(form: dict[str, Any]) -> DistressSignal:
    """
    Parse a Twilio WhatsApp inbound webhook form payload.

    Expected keys: Body, From, MessageSid, Latitude (opt), Longitude (opt).
    """
    raw        = form.get("Body", "")
    source_id  = form.get("From", "unknown")
    msg_sid    = form.get("MessageSid", "")
    received_at = datetime.now(timezone.utc)

    extra = {}
    if "Latitude" in form:
        extra["Latitude"]  = form["Latitude"]
        extra["Longitude"] = form.get("Longitude", "")

    signal = _whatsapp_parser.parse(
        raw=raw,
        source_channel="whatsapp",
        source_id=source_id,
        received_at=received_at,
        extra=extra,
    )
    signal.provider_message_id = str(msg_sid) or None
    return signal


def handle_twilio_sms(form: dict[str, Any]) -> DistressSignal:
    """
    Parse a Twilio SMS inbound webhook form payload.

    Expected keys: Body, From, MessageSid.
    """
    raw         = form.get("Body", "")
    source_id   = form.get("From", "unknown")
    received_at = datetime.now(timezone.utc)

    signal = _sms_parser.parse(
        raw=raw,
        source_channel="sms",
        source_id=source_id,
        received_at=received_at,
    )
    signal.provider_message_id = str(form.get("MessageSid", "")) or None
    return signal
