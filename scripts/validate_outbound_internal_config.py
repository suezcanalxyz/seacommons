#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from urllib.parse import urlsplit

from core.config import config
from core.net.outbound import OperatorInternalClient
from core.net.policy import OutboundError

Emit = Callable[[str], None]


def _safe_scheme(url: str) -> str:
    try:
        scheme = urlsplit(url).scheme.lower()
    except ValueError:
        return "other"
    return scheme if scheme in {"http", "https"} else "other"


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        raise OutboundError("invalid_request")
    return f"{parsed.scheme}://{parsed.netloc}"


def validate_configured_origin(
    name: str,
    url: str,
    *,
    emit: Emit = print,
    optional: bool = False,
) -> bool:
    value = str(url or "").strip()
    if not value and optional:
        return True
    scheme = _safe_scheme(value)
    try:
        OperatorInternalClient(_origin(value))
    except (OutboundError, ValueError):
        emit(f"{name} invalid {scheme}")
        return False
    emit(f"{name} valid {scheme}")
    return True


def _witness_endpoints(raw: str) -> list[str]:
    value = raw.strip()
    if not value:
        return []
    try:
        decoded = json.loads(value)
        if isinstance(decoded, list):
            return [str(item).strip() for item in decoded if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    checks: list[bool] = []
    checks.append(validate_configured_origin("API_INTERNAL_URL", config.API_INTERNAL_URL))
    checks.append(
        validate_configured_origin(
            "DRIFT_WORKER_URL", config.DRIFT_WORKER_URL, optional=True
        )
    )

    jwks_url = str(config.OIDC_JWKS_URL or "").strip()
    if not jwks_url and config.OIDC_ISSUER:
        jwks_url = f"{str(config.OIDC_ISSUER).rstrip('/')}/protocol/openid-connect/certs"
    checks.append(
        validate_configured_origin(
            "OIDC_JWKS", jwks_url, optional=not bool(config.AUTH_ENABLED)
        )
    )

    for index, endpoint in enumerate(_witness_endpoints(os.getenv("WITNESS_ENDPOINTS", "")), 1):
        checks.append(validate_configured_origin(f"WITNESS_ENDPOINT_{index}", endpoint))
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
