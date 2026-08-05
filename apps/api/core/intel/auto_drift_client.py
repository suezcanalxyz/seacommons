# SPDX-License-Identifier: AGPL-3.0-or-later
"""Trigger auto-drift over HTTP against the API's own /api/v1/intel/auto-drift.

Always goes over the network rather than importing the route handler
directly, so a monitor works identically whether it runs inside the API
process (single-VM deployment) or as a standalone process on a different
machine (API_INTERNAL_URL pointed at the API's host) — no special-casing
needed for either topology.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from core.config import config

logger = logging.getLogger(__name__)


def request_auto_drift(
    event_id: str,
    lat: float,
    lon: float,
    *,
    persons: Optional[int] = None,
    vessel_type: str = "rubber_boat",
) -> bool:
    """Best-effort request; failures are logged, never raised to the caller.

    Verified live: a cross-host deployment (monitors on one VM, API on
    another) pointed API_INTERNAL_URL at the *public* domain
    (api.seacommons.org) so the request would route correctly through the
    edge's host-based reverse proxy -- but that public domain is itself
    unreachable from server-to-server calls (times out; only client
    browsers reach it, via Vercel). Every auto-drift request from that host
    silently failed and swallowed the failure at DEBUG level, so a
    perfectly valid event just never got a drift cone, with nothing in the
    logs to explain why. API_INTERNAL_HOST_HEADER lets the URL point
    directly at the API host's real IP (bypassing the public domain
    entirely) while still sending the Host header the reverse proxy needs
    for vhost routing.
    """
    url = f"{config.API_INTERNAL_URL.rstrip('/')}/api/v1/intel/auto-drift"
    headers = {"Host": config.API_INTERNAL_HOST_HEADER} if config.API_INTERNAL_HOST_HEADER else {}
    body = {
        "intel_event_id": event_id,
        "lat": lat,
        "lon": lon,
        "vessel_type": vessel_type,
    }
    if persons is not None:
        body["persons"] = persons
    try:
        response = httpx.post(url, json=body, headers=headers, timeout=10.0)
        if response.status_code not in (200, 429):
            logger.warning("auto-drift request for %s failed: HTTP %s", event_id, response.status_code)
            return False
        return response.status_code == 200
    except Exception as exc:
        # Was DEBUG (invisible at default production log level) -- this
        # exact failure mode ran silently for who knows how long before
        # being found live. A dropped drift request is worth a WARNING.
        logger.warning("auto-drift request for %s failed: %s", event_id, exc)
        return False
