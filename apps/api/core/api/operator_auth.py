# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical authentication guard for the private operator ingestion surfaces.

Bearer requests use the verified Futures identity. The internal gateway
header remains a deliberately separate service-to-service compatibility path;
it must never be sent to public browser clients.
"""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from core.config import config


def require_operator_gateway(request: Request) -> None:
    """Fail closed unless a bearer identity or configured gateway secret passes."""
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        from core.security import require_futures_identity

        require_futures_identity(request)
        return

    expected = str(config.OPERATOR_GATEWAY_SECRET or "")
    if not expected:
        raise HTTPException(status_code=503, detail="Operator ingestion gateway is not configured")
    supplied = request.headers.get("x-seacommons-operator-gateway", "")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Operator gateway authentication required")
