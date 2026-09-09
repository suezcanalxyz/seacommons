# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import time

import jwt
import pytest
from core.config import config
from core.net.policy import OutboundError
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from core import security


def _key_material(kid: str):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return private, jwk


def _token(private, kid: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": "tester", "iat": now, "exp": now + 300, "aud": "seacommons", "iss": "http://issuer.internal"},
        private,
        algorithm="RS256",
        headers={"kid": kid},
    )


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def _configure_oidc(monkeypatch) -> None:
    monkeypatch.setattr(config, "OIDC_JWKS_URL", "http://127.0.0.1:8080/jwks")
    monkeypatch.setattr(config, "OIDC_ISSUER", "http://issuer.internal")
    monkeypatch.setattr(config, "OIDC_AUDIENCE", "seacommons")
    security._jwks = None


def test_jwks_fetch_binds_configured_private_origin_and_caches(monkeypatch) -> None:
    _configure_oidc(monkeypatch)
    captured = []
    _, jwk = _key_material("kid-1")

    class _Client:
        def __init__(self, origin, **kwargs):
            captured.append(("origin", origin, kwargs))

        def request(self, path, **kwargs):
            captured.append(("request", path, kwargs))
            return _Response({"keys": [jwk]})
    monkeypatch.setattr(security, "OperatorInternalClient", _Client, raising=False)
    first = security._load_jwks()
    second = security._load_jwks()

    assert first == second == {"keys": [jwk]}
    assert captured[0][1] == "http://127.0.0.1:8080"
    assert captured[1][1] == "/jwks"
    assert sum(1 for row in captured if row[0] == "request") == 1


def test_unknown_kid_forces_exactly_one_refresh(monkeypatch) -> None:
    _configure_oidc(monkeypatch)
    private, wanted = _key_material("kid-2")
    _, other = _key_material("kid-1")
    calls = 0

    class _Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            return _Response({"keys": [other if calls == 1 else wanted]})

    monkeypatch.setattr(security, "OperatorInternalClient", _Client, raising=False)
    principal = security.authenticate_token(_token(private, "kid-2"))
    assert principal.subject == "tester"
    assert calls == 2


def test_still_unknown_kid_fails_closed_after_one_refresh(monkeypatch) -> None:
    _configure_oidc(monkeypatch)
    private, _wanted = _key_material("kid-2")
    _, other = _key_material("kid-1")
    calls = 0

    class _Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            return _Response({"keys": [other]})

    monkeypatch.setattr(security, "OperatorInternalClient", _Client, raising=False)
    with pytest.raises(HTTPException) as exc:
        security.authenticate_token(_token(private, "kid-2"))
    assert exc.value.status_code == 401
    assert calls == 2


def test_jwks_outbound_failure_fails_auth_closed(monkeypatch) -> None:
    _configure_oidc(monkeypatch)
    private, _jwk = _key_material("kid-1")

    class _Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            raise OutboundError("blocked_target")
    monkeypatch.setattr(security, "OperatorInternalClient", _Client, raising=False)
    with pytest.raises(HTTPException) as exc:
        security.authenticate_token(_token(private, "kid-1"))
    assert exc.value.status_code == 401
