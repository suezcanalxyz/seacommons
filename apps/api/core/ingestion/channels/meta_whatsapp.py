# SPDX-License-Identifier: AGPL-3.0-or-later
"""Meta WhatsApp Cloud webhook parser."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.domain.live_contracts import PublicationStatus
from core.ingestion.parsers.whatsapp import WhatsAppParser
from core.ingestion.signal import DistressSignal

_parser = WhatsAppParser()
_MEDIA_TYPES = {"audio", "document", "image", "sticker", "video"}


def parse_meta_whatsapp(
    value: dict[str, Any], connector: dict[str, Any]
) -> list[DistressSignal]:
    contacts = {
        str(item.get("wa_id") or ""): str((item.get("profile") or {}).get("name") or "")
        for item in value.get("contacts") or []
    }
    signals: list[DistressSignal] = []
    for message in value.get("messages") or []:
        source_id = str(message.get("from") or "unknown")
        message_type = str(message.get("type") or "unknown")
        raw, extra, attachments = _content(message_type, message)
        try:
            received_at = datetime.fromtimestamp(
                int(message.get("timestamp") or 0), timezone.utc
            )
        except (TypeError, ValueError, OSError):
            received_at = datetime.now(timezone.utc)
        signal = _parser.parse(
            raw=raw,
            source_channel="whatsapp",
            source_id=source_id,
            received_at=received_at,
            extra=extra,
        )
        signal.organization_id = connector["organization_id"]
        signal.connector_id = connector["connector_id"]
        signal.provider_message_id = str(message.get("id") or "") or None
        signal.source_name = contacts.get(source_id) or connector.get("display_name")
        signal.attachments = attachments
        # Raw partner messages remain private until an authorised operator publishes.
        signal.publication_status = PublicationStatus.PRIVATE
        signals.append(signal)
    return signals


def _content(
    message_type: str, message: dict[str, Any]
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    extra: dict[str, Any] = {}
    attachments: list[dict[str, Any]] = []
    content = message.get(message_type) or {}
    if message_type == "text":
        return str(content.get("body") or ""), extra, attachments
    if message_type == "location":
        extra = {
            "Latitude": content.get("latitude"),
            "Longitude": content.get("longitude"),
        }
        label = content.get("name") or content.get("address") or "shared location"
        return f"[{label}]", extra, attachments
    if message_type in _MEDIA_TYPES:
        attachment = {
            key: content[key]
            for key in ("id", "mime_type", "sha256", "caption", "filename")
            if content.get(key) is not None
        }
        attachment["type"] = message_type
        attachments.append(attachment)
        return str(content.get("caption") or f"[{message_type}]"), extra, attachments
    if message_type in {"button", "interactive"}:
        body = (
            content.get("text")
            or (content.get("button_reply") or {}).get("title")
            or (content.get("list_reply") or {}).get("title")
            or f"[{message_type}]"
        )
        return str(body), extra, attachments
    return f"[unsupported WhatsApp message: {message_type}]", extra, attachments
