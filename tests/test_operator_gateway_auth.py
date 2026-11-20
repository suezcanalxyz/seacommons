"""Regression coverage for shared operator access policy."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from core.api.operator_auth import require_operator_gateway
from core.config import config


def request(headers: dict[str, str] | None = None) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "scheme": "https",
        "path": "/api/v1/operator/ingestion/dashboard",
        "root_path": "",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    })


def test_gateway_fails_closed_when_secret_unconfigured(monkeypatch):
    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", None)
    with pytest.raises(HTTPException) as exc:
        require_operator_gateway(request())
    assert exc.value.status_code == 503


def test_gateway_requires_exact_secret(monkeypatch):
    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "correct-secret")
    for headers in ({}, {"x-seacommons-operator-gateway": "almost-right"}):
        with pytest.raises(HTTPException) as exc:
            require_operator_gateway(request(headers))
        assert exc.value.status_code == 401
    require_operator_gateway(request({"x-seacommons-operator-gateway": "correct-secret"}))


def test_bearer_auth_is_always_checked_even_with_valid_gateway_header(monkeypatch):
    from core import security
    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "correct-secret")
    calls = []

    def validate(req):
        calls.append(req)
        raise HTTPException(status_code=403, detail="invalid identity")

    monkeypatch.setattr(security, "require_futures_identity", validate)
    with pytest.raises(HTTPException) as exc:
        require_operator_gateway(request({
            "authorization": "Bearer invalid",
            "x-seacommons-operator-gateway": "correct-secret",
        }))
    assert exc.value.status_code == 403
    assert len(calls) == 1


def test_valid_bearer_delegates_to_verified_identity(monkeypatch):
    from core import security
    monkeypatch.setattr(config, "OPERATOR_GATEWAY_SECRET", "")
    calls = []
    monkeypatch.setattr(security, "require_futures_identity", calls.append)
    req = request({"authorization": "Bearer valid-token"})
    require_operator_gateway(req)
    assert calls == [req]
