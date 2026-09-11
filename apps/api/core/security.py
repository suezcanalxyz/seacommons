# SPDX-License-Identifier: AGPL-3.0-or-later
"""OIDC authentication and coarse API authorization.

Keycloak is the reference provider, but only standard JWT/OIDC features are used.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from fastapi import HTTPException, Request, WebSocket, status

from core.config import config
from core.net.outbound import OperatorInternalClient
from core.net.policy import JSON_TEXT, OutboundError


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]
    claims: dict


_jwks: tuple[float, dict] | None = None


def _claim(claims: dict, dotted_path: str):
    value: object = claims
    for part in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _jwks_url() -> str:
    if config.OIDC_JWKS_URL:
        return config.OIDC_JWKS_URL
    return f"{config.OIDC_ISSUER.rstrip('/')}/protocol/openid-connect/certs"


def _jwks_origin_and_target() -> tuple[str, str]:
    parsed = urlsplit(_jwks_url())
    if not parsed.scheme or not parsed.netloc:
        raise OutboundError("invalid_request")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    return origin, target


def _load_jwks(force_refresh: bool = False) -> dict:
    global _jwks
    now = time.time()
    if not force_refresh and _jwks and now - _jwks[0] < 300:
        return _jwks[1]
    origin, target = _jwks_origin_and_target()
    response = OperatorInternalClient(origin, timeout=5.0).request(
        target, contract=JSON_TEXT
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        raise OutboundError("upstream_error")
    _jwks = (now, data)
    return data


def _signing_key_from_jwks(token: str, jwks: dict):
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise KeyError("missing kid")
    for item in jwks.get("keys", []):
        if isinstance(item, dict) and item.get("kid") == kid:
            return jwt.PyJWK.from_dict(item).key
    raise KeyError("unknown kid")


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
        jwks = _load_jwks()
        try:
            key = _signing_key_from_jwks(token, jwks)
        except KeyError:
            key = _signing_key_from_jwks(token, _load_jwks(force_refresh=True))
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
