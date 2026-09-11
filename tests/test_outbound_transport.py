# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import asyncio
import ipaddress
from contextlib import AbstractContextManager
from typing import ClassVar

import pytest
from core.net.outbound import OutboundResponse, request
from core.net.policy import (
    IMAGE,
    JSON_TEXT,
    NormalizedOrigin,
    OutboundError,
    TrustProfile,
    ValidatedTarget,
)
from core.net.transport import (
    TimeoutBudget,
    TransportResult,
    async_send_pinned,
    send_pinned,
)


class _SyncResponse:
    def __init__(self, status: int = 200, headers=None, chunks=None):
        self.status = status
        self.headers = headers or [(b"content-type", b"application/json")]
        self._chunks = list(chunks or [b"{}"])
        self.closed = False

    def iter_stream(self):
        yield from self._chunks

    def close(self):
        self.closed = True


class _SyncStream(AbstractContextManager):
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self.response

    def __exit__(self, *_args):
        self.response.close()
        return False


class _Pool:
    captured: ClassVar[dict] = {}
    response = _SyncResponse()

    def __init__(self, **kwargs):
        self.captured["pool_kwargs"] = kwargs

    def stream(self, method, url, *, headers=None, content=None, extensions=None):
        self.captured.update(
            method=method,
            url=url,
            headers=headers,
            content=content,
            extensions=extensions,
        )
        return _SyncStream(self.response)

    def close(self):
        self.captured["closed"] = True


def _target(host: str = "example.com", address: str = "93.184.216.34") -> ValidatedTarget:
    return ValidatedTarget(
        origin=NormalizedOrigin("https", host, 443, host),
        addresses=(ipaddress.ip_address(address),),
    )


def test_send_pinned_uses_validated_ip_and_preserves_host_and_sni(monkeypatch) -> None:
    from core.net import transport

    _Pool.captured = {}
    _Pool.response = _SyncResponse(chunks=[b'{"ok":true}'])
    monkeypatch.setattr(transport.httpcore, "ConnectionPool", _Pool)

    result = send_pinned(
        _target(),
        "https://example.com/path?q=1",
        method="GET",
        contract=JSON_TEXT,
        timeout=TimeoutBudget.from_value(5),
    )

    assert result.body == b'{"ok":true}'
    assert _Pool.captured["url"] == "https://93.184.216.34:443/path?q=1"
    headers = dict(_Pool.captured["headers"])
    assert headers[b"host"] == b"example.com"
    assert _Pool.captured["extensions"]["sni_hostname"] == "example.com"


def test_timeout_budget_is_finite_and_capped() -> None:
    timeout = TimeoutBudget.from_value(999)
    assert timeout.connect == 120
    assert timeout.read == 120
    assert timeout.write == 120
    assert timeout.pool == 120
    assert TimeoutBudget.from_value(90).read == 90


def test_send_pinned_rejects_declared_oversize_before_read(monkeypatch) -> None:
    from core.net import transport

    _Pool.captured = {}
    _Pool.response = _SyncResponse(
        headers=[
            (b"content-type", b"image/png"),
            (b"content-length", str(IMAGE.max_bytes + 1).encode()),
        ],
        chunks=[b"must-not-be-read"],
    )
    monkeypatch.setattr(transport.httpcore, "ConnectionPool", _Pool)

    with pytest.raises(OutboundError) as exc:
        send_pinned(_target(), "https://example.com/a.png", method="GET", contract=IMAGE)
    assert exc.value.code == "response_too_large"
    assert _Pool.response.closed is True


def test_send_pinned_stops_stream_over_cap(monkeypatch) -> None:
    from core.net import transport

    tiny = type(IMAGE)("tiny", 4, ())
    _Pool.response = _SyncResponse(chunks=[b"abc", b"de"])
    monkeypatch.setattr(transport.httpcore, "ConnectionPool", _Pool)
    with pytest.raises(OutboundError) as exc:
        send_pinned(_target(), "https://example.com/a", method="GET", contract=tiny)
    assert exc.value.code == "response_too_large"


def test_image_contract_rejects_non_image_content_type(monkeypatch) -> None:
    from core.net import transport

    _Pool.response = _SyncResponse(headers=[(b"content-type", b"text/html")], chunks=[b"x"])
    monkeypatch.setattr(transport.httpcore, "ConnectionPool", _Pool)
    with pytest.raises(OutboundError) as exc:
        send_pinned(_target(), "https://example.com/a", method="GET", contract=IMAGE)
    assert exc.value.code == "invalid_content_type"


def test_public_redirect_to_private_is_blocked_before_second_connection(monkeypatch) -> None:
    from core.net import outbound

    sent: list[str] = []

    def resolver(host: str, _port: int) -> list[str]:
        return ["10.0.0.7"] if host == "private.example" else ["93.184.216.34"]

    def fake_send(target, url, **_kwargs):
        sent.append(url)
        return TransportResult(302, {"location": "https://private.example/secret"}, b"")

    monkeypatch.setattr(outbound, "send_pinned", fake_send)
    with pytest.raises(OutboundError) as exc:
        request(
            "https://public.example/start",
            profile=TrustProfile.PUBLIC_UNTRUSTED,
            resolver=resolver,
        )
    assert exc.value.code == "blocked_target"
    assert sent == ["https://public.example/start"]


def test_public_fixed_rejects_redirect_outside_allowlist(monkeypatch) -> None:
    from core.net import outbound

    def resolver(_host: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(
        outbound,
        "send_pinned",
        lambda *_args, **_kwargs: TransportResult(
            302, {"location": "https://other.example/next"}, b""
        ),
    )
    with pytest.raises(OutboundError) as exc:
        request(
            "https://fixed.example/start",
            profile=TrustProfile.PUBLIC_FIXED,
            allowed_origins=["https://fixed.example"],
            resolver=resolver,
        )
    assert exc.value.code == "redirect_blocked"


def test_redirect_loop_is_bounded(monkeypatch) -> None:
    from core.net import outbound

    monkeypatch.setattr(
        outbound,
        "send_pinned",
        lambda *_args, **_kwargs: TransportResult(
            302, {"location": "https://example.com/start"}, b""
        ),
    )
    with pytest.raises(OutboundError) as exc:
        request(
            "https://example.com/start",
            resolver=lambda *_: ["93.184.216.34"],
        )
    assert exc.value.code == "redirect_limit"


def test_post_redirect_is_never_auto_followed(monkeypatch) -> None:
    from core.net import outbound

    monkeypatch.setattr(
        outbound,
        "send_pinned",
        lambda *_args, **_kwargs: TransportResult(
            307, {"location": "https://fixed.example/next"}, b""
        ),
    )
    with pytest.raises(OutboundError) as exc:
        request(
            "https://fixed.example/start",
            method="POST",
            profile=TrustProfile.PUBLIC_FIXED,
            allowed_origins=["https://fixed.example"],
            resolver=lambda *_: ["93.184.216.34"],
            body=b"{}",
        )
    assert exc.value.code == "redirect_blocked"


def test_outbound_response_json_and_raise_for_status_are_bounded() -> None:
    response = OutboundResponse(200, {"content-type": "application/json"}, b'{"ok": true}')
    assert response.json() == {"ok": True}
    response.raise_for_status()

    with pytest.raises(OutboundError) as exc:
        OutboundResponse(503, {}, b"private upstream body").raise_for_status()
    assert exc.value.code == "upstream_error"
    assert "private upstream body" not in str(exc.value)


class _AsyncResponse:
    status = 200
    headers: ClassVar[list[tuple[bytes, bytes]]] = [(b"content-type", b"application/json")]

    async def aiter_stream(self):
        yield b"{}"

    async def aclose(self):
        return None


class _AsyncContext:
    async def __aenter__(self):
        return _AsyncResponse()

    async def __aexit__(self, *_args):
        return False


class _AsyncPool:
    captured: ClassVar[dict] = {}

    def __init__(self, **kwargs):
        self.captured["pool_kwargs"] = kwargs

    def stream(self, method, url, *, headers=None, content=None, extensions=None):
        self.captured.update(url=url, headers=headers, extensions=extensions)
        return _AsyncContext()

    async def aclose(self):
        return None


def test_async_send_pinned_preserves_validated_destination_and_sni(monkeypatch) -> None:
    from core.net import transport

    _AsyncPool.captured = {}
    monkeypatch.setattr(transport.httpcore, "AsyncConnectionPool", _AsyncPool)

    result = asyncio.run(
        async_send_pinned(
            _target(),
            "https://example.com/data",
            method="GET",
            contract=JSON_TEXT,
            timeout=TimeoutBudget.from_value(5),
        )
    )
    assert result.body == b"{}"
    assert _AsyncPool.captured["url"] == "https://93.184.216.34:443/data"
    headers = dict(_AsyncPool.captured["headers"])
    assert headers[b"host"] == b"example.com"
    assert _AsyncPool.captured["extensions"]["sni_hostname"] == "example.com"


def test_operator_internal_client_binds_configured_origin_and_rejects_absolute_paths(monkeypatch) -> None:
    from core.net import outbound
    from core.net.outbound import OperatorInternalClient

    sent: list[tuple[str, str]] = []

    def fake_send(target, url, **_kwargs):
        sent.append((target.origin.host, url))
        return TransportResult(200, {"content-type": "application/json"}, b"{}")

    monkeypatch.setattr(outbound, "send_pinned", fake_send)
    client = OperatorInternalClient(
        "http://127.0.0.1:8100",
        resolver=lambda *_: ["127.0.0.1"],
    )
    assert client.request("/health").status_code == 200
    assert sent == [("127.0.0.1", "http://127.0.0.1:8100/health")]

    with pytest.raises(OutboundError) as exc:
        client.request("https://evil.example/escape")
    assert exc.value.code == "invalid_request"
    assert len(sent) == 1


def test_fixed_origin_client_never_leaves_declared_origin(monkeypatch) -> None:
    from core.net import outbound
    from core.net.outbound import FixedOriginClient

    sent: list[str] = []
    monkeypatch.setattr(
        outbound,
        "send_pinned",
        lambda _target, url, **_kwargs: (
            sent.append(url) or TransportResult(200, {"content-type": "application/json"}, b"{}")
        ),
    )
    client = FixedOriginClient(
        ["https://fixed.example"],
        resolver=lambda *_: ["93.184.216.34"],
    )
    assert client.request("https://fixed.example/data").status_code == 200
    with pytest.raises(OutboundError) as exc:
        client.request("https://other.example/data")
    assert exc.value.code == "blocked_target"
    assert sent == ["https://fixed.example/data"]


def test_operator_internal_client_does_not_follow_redirects(monkeypatch) -> None:
    from core.net import outbound
    from core.net.outbound import OperatorInternalClient

    sent: list[str] = []
    monkeypatch.setattr(
        outbound,
        "send_pinned",
        lambda _target, url, **_kwargs: (
            sent.append(url) or TransportResult(302, {"location": "/other"}, b"")
        ),
    )
    client = OperatorInternalClient(
        "http://127.0.0.1:8100",
        resolver=lambda *_: ["127.0.0.1"],
    )
    with pytest.raises(OutboundError) as exc:
        client.request("/health")
    assert exc.value.code == "redirect_blocked"
    assert sent == ["http://127.0.0.1:8100/health"]


def test_async_operator_internal_client_uses_bound_origin(monkeypatch) -> None:
    from core.net import outbound
    from core.net.outbound import AsyncOperatorInternalClient

    sent: list[str] = []

    async def fake_send(_target, url, **_kwargs):
        sent.append(url)
        return TransportResult(200, {"content-type": "application/json"}, b"{}")

    monkeypatch.setattr(outbound, "async_send_pinned", fake_send)
    client = AsyncOperatorInternalClient(
        "http://127.0.0.1:8100",
        resolver=lambda *_: ["127.0.0.1"],
    )
    response = asyncio.run(client.request("/health"))
    assert response.status_code == 200
    assert sent == ["http://127.0.0.1:8100/health"]
