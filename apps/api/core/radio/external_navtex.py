"""Read-only NAVTEX secondary source adapter; never classified as RF/DSC evidence.

Source: https://navtex.online/feeds
API polling is permitted at most once per minute by upstream terms.
Production scheduling must enforce this globally across workers.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

from core.net.outbound import FixedOriginClient

BASE = "https://navtex.online"
NAVAREAS = frozenset(("I", "II", "III", "IV", "V", "VI", "VII", "VIII",
    "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII",
    "XIX", "XX", "XXI"))


def normalize_navtex_message(row: dict) -> dict:
    """Preserve upstream lineage and labels, without inventing geometry."""
    external_id = str(row.get("id") or "")
    if not external_id:
        raise ValueError("NAVTEX message without ID")
    station = row.get("station") or {}
    if not isinstance(station, dict):
        station = {}
    plain = row.get("plain") or {}
    if not isinstance(plain, dict):
        plain = {}
    return {
        "source": "navtex_online",
        "source_class": "secondary_maritime_safety_information",
        "independent_rf_reception": False,
        "is_dsc_decode": False,
        "external_id": external_id,
        "original_url": row.get("url") or f"{BASE}/messages/{external_id}",
        "station_id": station.get("id"),
        "navarea": station.get("navarea"),
        "first_seen": row.get("firstSeen"),
        "last_seen": row.get("lastSeen"),
        "status": row.get("status") if isinstance(row.get("status"), str) else "unknown",
        "original_text": row.get("text") or plain.get("text"),
        "positions_unverified": row.get("positions") or [],
        "upstream_sources": row.get("sources") or [],
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_navtex_messages(*, navarea: str = "III", limit: int = 50,
                          timeout: float = 8.0) -> list[dict]:
    """Get a bounded page. Callers MUST enforce <=1 request/min globally."""
    if navarea not in NAVAREAS:
        raise ValueError("invalid NAVAREA")
    if not 1 <= limit <= 200:
        raise ValueError("limit must be 1..200")
    url = f"{BASE}/api/v1/messages?" + urlencode({"navarea": navarea, "limit": limit})
    client = FixedOriginClient((BASE,), timeout=timeout)
    response = client.request(
        url,
        headers={"User-Agent": "SeaCommons/1.0 NAVTEX read-only"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise ValueError("unexpected NAVTEX response")
    return [normalize_navtex_message(row) for row in payload["messages"]
            if isinstance(row, dict)]

# An in-process shared cache gates public reads and all upstream requests.
# Oracle runs this app as one uvicorn worker; additional workers must migrate
# the lock to Redis before enabling this on a multi-process deployment.
_cache_lock = threading.Lock()
_cache_next_request = 0.0
_cache_rows: list[dict] = []
_cache_fetched_at: str | None = None
_cache_error: str | None = None


def public_navtex_snapshot() -> dict:
    """Bounded NAVAREA III published warnings, never first-party RF observations.

    At most one upstream request in any 65-second window (including failures).
    Last good records are retained on transient provider outage.
    """
    global _cache_next_request, _cache_rows, _cache_fetched_at, _cache_error
    with _cache_lock:
        now = time.monotonic()
        if now >= _cache_next_request:
            _cache_next_request = now + 65.0
            try:
                rows = fetch_navtex_messages(navarea="III", limit=50)
                _cache_rows = rows
                _cache_fetched_at = datetime.now(timezone.utc).isoformat()
                _cache_error = None
            except Exception:
                _cache_error = "provider_unavailable"
        return {
            "source": "navtex_online",
            "source_class": "secondary_maritime_safety_information",
            "independent_rf_reception": False,
            "scope": "NAVAREA_III",
            "upstream": f"{BASE}/feeds",
            "fetched_at": _cache_fetched_at,
            "state": "degraded" if _cache_error else ("live" if _cache_fetched_at else "unavailable"),
            "messages": list(_cache_rows),
            "warning": "Public secondary copies; not first-party radio reception and not for navigation.",
        }
