from __future__ import annotations
import logging
import threading
import time
from typing import Any

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


_alert_cooldowns: dict[str, float] = {}
_alert_lock = threading.Lock()


def _cooldown_ok(key: str, window_s: float) -> bool:
    now = time.monotonic()
    with _alert_lock:
        last = _alert_cooldowns.get(key, 0.0)
        if now - last < window_s:
            return False
        _alert_cooldowns[key] = now
        # opportunistic prune
        if len(_alert_cooldowns) > 512:
            for stale in [k for k, v in _alert_cooldowns.items() if now - v > window_s * 4]:
                _alert_cooldowns.pop(stale, None)
    return True


def notify_alert(alert: dict[str, Any]) -> bool:
    """Outbound notification for a correlated OSINT alert.

    ``alert`` carries ``alert_type``, ``domain``, ``confidence``, ``lat`` /
    ``lon``, ``contributing_sources`` and ``cluster_id`` (see
    ``core.intel.fusion``). No-op when neither channel is configured; rate
    limited per ``cluster_id`` so one evolving incident does not spam.
    """
    cooldown_s = float(getattr(config, "FUSION_NOTIFY_COOLDOWN_S", 1800) or 1800)
    key = str(alert.get("cluster_id") or alert.get("id") or "")
    if key and not _cooldown_ok(key, cooldown_s):
        return False
    lat, lon = alert.get("lat"), alert.get("lon")
    where = f"{lat:.3f},{lon:.3f}" if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) else "position unknown"
    sources = ", ".join(alert.get("contributing_sources") or []) or "n/a"
    confidence = alert.get("confidence")
    conf_str = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "n/a"
    notice = (
        "SEACOMMONS · OSINT ALERT\n"
        f"{alert.get('alert_type', 'correlated_alert')}  [{alert.get('domain', 'sar')}]\n"
        f"confidence {conf_str}  ·  {where}\n"
        f"sources: {sources}"
    )
    sent = telegram(notice)
    sent = whatsapp(notice) or sent
    return sent
