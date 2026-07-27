# SPDX-License-Identifier: AGPL-3.0-or-later
"""OIDC authentication and coarse API authorization.

Keycloak is the reference provider, but only standard JWT/OIDC features are used.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.request import urlopen

import jwt
from fastapi import HTTPException, Request, WebSocket, status

from core.config import config


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]
    claims: dict


_jwks: tuple[float, dict] | None = None


def _claim(claims: dict, dotted_path: str):
    value = claims
    for part in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _jwks_url() -> str:
    if config.OIDC_JWKS_URL:
        return config.OIDC_JWKS_URL
    return f"{config.OIDC_ISSUER.rstrip('/')}/protocol/openid-connect/certs"


def _load_jwks() -> dict:
    global _jwks
    now = time.time()
    if _jwks and now - _jwks[0] < 300:
        return _jwks[1]
    with urlopen(_jwks_url(), timeout=5) as response:  # nosec: operator-configured HTTPS URL
        data = json.load(response)
    _jwks = (now, data)
    return data


def authenticate(request: Request) -> Principal | None:
    if not config.AUTH_ENABLED:
        return Principal("local-development", frozenset({"administrator"}), {})
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    return authenticate_token(token)


def authenticate_token(token: str) -> Principal:
    try:
        key = jwt.PyJWKClient(_jwks_url(), cache_keys=True).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256", "ES256"],
            audience=config.OIDC_AUDIENCE,
            issuer=config.OIDC_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc
    roles_value = _claim(claims, config.OIDC_ROLES_CLAIM) or claims.get("roles") or []
    if isinstance(roles_value, str):
        roles_value = roles_value.split()
    if not roles_value:
        roles_value = config.OIDC_DEFAULT_ROLES
    return Principal(str(claims["sub"]), frozenset(map(str, roles_value)), claims)


async def authorize_websocket(websocket: WebSocket, allowed: set[str]) -> str | None:
    """Authorize before accept. Browser clients pass JWT as second WS subprotocol."""
    if not config.AUTH_ENABLED:
        return None
    protocols = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    if len(protocols) != 2 or protocols[0] != "bearer":
        await websocket.close(code=4401, reason="Authentication required")
        return "closed"
    try:
        principal = authenticate_token(protocols[1])
    except HTTPException:
        await websocket.close(code=4401, reason="Invalid access token")
        return "closed"
    if not (principal.roles & allowed):
        await websocket.close(code=4403, reason="Insufficient role")
        return "closed"
    return "bearer"


def require_roles(request: Request, allowed: set[str]) -> Principal:
    principal = authenticate(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not (principal.roles & allowed):
        raise HTTPException(status_code=403, detail="Insufficient role")
    return principal


WRITE_ROLES = {"operator", "case_manager", "data_steward", "administrator", "integration_service"}
READ_ROLES = WRITE_ROLES | {"analyst", "researcher"}


def validate_production_security() -> None:
    if config.RUNTIME_PROFILE.lower() not in {"production", "prod"}:
        return
    missing = []
    if not config.AUTH_ENABLED:
        missing.append("AUTH_ENABLED=true")
    if not config.OIDC_ISSUER:
        missing.append("OIDC_ISSUER")
    if not config.OIDC_AUDIENCE:
        missing.append("OIDC_AUDIENCE")
    if not config.OBJECT_STORAGE_ENDPOINT:
        missing.append("OBJECT_STORAGE_ENDPOINT")
    if config.JOB_EXECUTION_MODE != "queue":
        missing.append("JOB_EXECUTION_MODE=queue")
    if missing:
        raise RuntimeError("Unsafe production configuration: " + ", ".join(missing))
