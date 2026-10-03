"""Invite-only partner authentication. No development bypass and no shared roles."""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from fastapi import HTTPException, Request

from core.config import config
from core.net.outbound import OperatorInternalClient
from core.net.policy import JSON_TEXT
from core.security import _signing_key_from_jwks


@dataclass(frozen=True)
class Partner:
    subject: str
    email: str
    organization_id: str
    role: str

    @property
    def can_edit(self) -> bool:
        return self.role in {"editor", "administrator"}


_cache: tuple[str, float, dict] | None = None


def _partner_jwks(force: bool = False) -> dict:
    global _cache
    issuer = config.PARTNER_AUTH_ISSUER.rstrip("/")
    parsed = urlsplit(issuer)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Invalid partner issuer")
    now = time.time()
    if not force and _cache and _cache[0] == issuer and now - _cache[1] < 300:
        return _cache[2]
    origin = f"https://{parsed.netloc}"
    response = OperatorInternalClient(origin, timeout=5.0).request(
        f"{parsed.path}/.well-known/jwks.json", contract=JSON_TEXT
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        raise ValueError("Invalid partner key set")
    _cache = (issuer, now, data)
    return data


def require_partner(request: Request, *, edit: bool = False) -> Partner:
    if not config.PARTNER_AUTH_ENABLED or not config.PARTNER_AUTH_ISSUER:
        raise HTTPException(503, "Partner access is not configured")
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in to continue")
    token = header.split(" ", 1)[1].strip()
    try:
        try:
            key = _signing_key_from_jwks(token, _partner_jwks())
        except KeyError:
            key = _signing_key_from_jwks(token, _partner_jwks(force=True))
        claims = jwt.decode(
            token, key, algorithms=["RS256", "ES256"],
            issuer=config.PARTNER_AUTH_ISSUER.rstrip("/"),
            audience=config.PARTNER_AUTH_AUDIENCE,
            options={"require": ["sub", "iat", "exp", "email"]},
        )
    except Exception as exc:
        raise HTTPException(401, "Invalid or expired session") from exc
    email = str(claims.get("email", "")).strip().lower()
    account = config.PARTNER_ACCOUNTS.get(email)
    if (
        not account or claims.get("is_anonymous") is True
        or account.get("subject") != claims["sub"]
        or not account.get("organization_id")
        or account.get("role") not in {"viewer", "editor", "administrator"}
    ):
        raise HTTPException(403, "Partner access has not been authorised")
    partner = Partner(str(claims["sub"]), email, account["organization_id"], account["role"])
    if edit and not partner.can_edit:
        raise HTTPException(403, "Editing access is required")
    return partner
