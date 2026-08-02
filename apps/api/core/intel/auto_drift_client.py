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
    """Best-effort request; failures are logged, never raised to the caller."""
    url = f"{config.API_INTERNAL_URL.rstrip('/')}/api/v1/intel/auto-drift"
    body = {
        "intel_event_id": event_id,
        "lat": lat,
        "lon": lon,
        "vessel_type": vessel_type,
    }
    if persons is not None:
        body["persons"] = persons
    try:
        response = httpx.post(url, json=body, timeout=10.0)
        if response.status_code not in (200, 429):
            logger.warning("auto-drift request for %s failed: HTTP %s", event_id, response.status_code)
            return False
        return response.status_code == 200
    except Exception as exc:
        logger.debug("auto-drift request for %s failed: %s", event_id, exc)
        return False
