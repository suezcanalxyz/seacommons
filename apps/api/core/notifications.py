from __future__ import annotations
import logging
import httpx
from core.config import config

logger = logging.getLogger(__name__)


def telegram(text: str) -> bool:
    """Best-effort outbound notification. Never blocks a case transaction."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_OPERATIONS_CHAT_ID:
        return False
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": config.TELEGRAM_OPERATIONS_CHAT_ID, "text": text,
                  "disable_web_page_preview": True}, timeout=8,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Telegram notification failed: %s", exc)
        return False


def whatsapp(text: str) -> bool:
    """Send an operational WhatsApp message through Twilio when fully configured."""
    if not (
        config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN
        and config.TWILIO_WHATSAPP_NUMBER and config.TWILIO_OPERATIONS_WHATSAPP_TO
    ):
        return False
    sender = config.TWILIO_WHATSAPP_NUMBER
    recipient = config.TWILIO_OPERATIONS_WHATSAPP_TO
    if not sender.startswith("whatsapp:"):
        sender = f"whatsapp:{sender}"
    if not recipient.startswith("whatsapp:"):
        recipient = f"whatsapp:{recipient}"
    try:
        response = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages.json",
            data={"From": sender, "To": recipient, "Body": text},
            auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
            timeout=8,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("WhatsApp notification failed: %s", exc)
        return False
