# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

import httpcore

from core.net.policy import OutboundError, ResponseContract, ValidatedTarget


@dataclass(frozen=True)
class TimeoutBudget:
    connect: float
    read: float
    write: float
    pool: float

    @classmethod
    def from_value(cls, value: float | "TimeoutBudget" | None = None) -> "TimeoutBudget":
        if isinstance(value, TimeoutBudget):
            return cls(
                min(120.0, max(0.001, value.connect)),
                min(120.0, max(0.001, value.read)),
                min(120.0, max(0.001, value.write)),
                min(120.0, max(0.001, value.pool)),
            )
        base_value = 15.0 if value is None else value
        bounded = min(120.0, max(0.001, base_value))
        return cls(bounded, bounded, bounded, bounded)

    def as_extension(self) -> dict[str, float]:
        return {"connect": self.connect, "read": self.read, "write": self.write, "pool": self.pool}


@dataclass(frozen=True)
class TransportResult:
    status_code: int
    headers: dict[str, str]
    body: bytes


def _pinned_url(target: ValidatedTarget, original_url: str) -> str:
    parsed = urlsplit(original_url)
    address = target.addresses[0]
    host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return f"{target.origin.scheme}://{host}:{target.origin.port}{path}"


def _request_headers(
    target: ValidatedTarget,
    headers: Mapping[str, str] | None,
    *,
    host_header: str | None,
) -> list[tuple[bytes, bytes]]:
    prepared: list[tuple[bytes, bytes]] = []
    for key, value in (headers or {}).items():
        if key.lower() == "host":
            continue
        prepared.append((key.lower().encode("ascii"), str(value).encode("latin-1")))
    authority = host_header or target.origin.authority
    prepared.append((b"host", authority.encode("ascii")))
    return prepared


def _decode_headers(headers) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in headers or []:
        name = key.decode("latin-1").lower() if isinstance(key, bytes) else str(key).lower()
        text = value.decode("latin-1") if isinstance(value, bytes) else str(value)
        result[name] = text
    return result


def _validate_response_headers(status_code: int, headers: dict[str, str], contract: ResponseContract) -> None:
    if 300 <= status_code < 400:
        return
    length = headers.get("content-length")
    if length:
        try:
            if int(length) > contract.max_bytes:
                raise OutboundError("response_too_large")
        except ValueError:
            pass
    if contract.content_type_prefixes:
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if not any(content_type.startswith(prefix) for prefix in contract.content_type_prefixes):
            raise OutboundError("invalid_content_type")


def _map_httpcore_error(exc: Exception) -> OutboundError:
    if isinstance(exc, (httpcore.ConnectTimeout, httpcore.ReadTimeout, httpcore.WriteTimeout, httpcore.PoolTimeout)):
        return OutboundError("timeout")
    if isinstance(exc, httpcore.ConnectError) and isinstance(exc.__cause__, ssl.SSLError):
        return OutboundError("tls_failed")
    return OutboundError("upstream_error")


def _read_bounded(response, contract: ResponseContract) -> bytes:
    payload = bytearray()
    for chunk in response.iter_stream():
        payload.extend(chunk)
        if len(payload) > contract.max_bytes:
            raise OutboundError("response_too_large")
    return bytes(payload)


async def _aread_bounded(response, contract: ResponseContract) -> bytes:
    payload = bytearray()
    async for chunk in response.aiter_stream():
        payload.extend(chunk)
        if len(payload) > contract.max_bytes:
            raise OutboundError("response_too_large")
    return bytes(payload)


def send_pinned(
    target: ValidatedTarget,
    original_url: str,
    *,
    method: str,
    contract: ResponseContract,
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    host_header: str | None = None,
    timeout: float | TimeoutBudget | None = None,
) -> TransportResult:
    budget = TimeoutBudget.from_value(timeout)
    pool = httpcore.ConnectionPool(max_connections=1, max_keepalive_connections=0, retries=0)
    try:
        with pool.stream(
            method.upper(),
            _pinned_url(target, original_url),
            headers=_request_headers(target, headers, host_header=host_header),
            content=body,
            extensions={
                "timeout": budget.as_extension(),
                **({"sni_hostname": target.origin.host} if target.origin.scheme == "https" else {}),
            },
        ) as response:
            decoded = _decode_headers(response.headers)
            _validate_response_headers(response.status, decoded, contract)
            body_bytes = b"" if 300 <= response.status < 400 else _read_bounded(response, contract)
            return TransportResult(response.status, decoded, body_bytes)
    except OutboundError:
        raise
    except Exception as exc:
        raise _map_httpcore_error(exc) from exc
    finally:
        pool.close()


async def async_send_pinned(
    target: ValidatedTarget,
    original_url: str,
    *,
    method: str,
    contract: ResponseContract,
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    host_header: str | None = None,
    timeout: float | TimeoutBudget | None = None,
) -> TransportResult:
    budget = TimeoutBudget.from_value(timeout)
    pool = httpcore.AsyncConnectionPool(max_connections=1, max_keepalive_connections=0, retries=0)
    try:
        async with pool.stream(
            method.upper(),
            _pinned_url(target, original_url),
            headers=_request_headers(target, headers, host_header=host_header),
            content=body,
            extensions={
                "timeout": budget.as_extension(),
                **({"sni_hostname": target.origin.host} if target.origin.scheme == "https" else {}),
            },
        ) as response:
            decoded = _decode_headers(response.headers)
            _validate_response_headers(response.status, decoded, contract)
            body_bytes = b"" if 300 <= response.status < 400 else await _aread_bounded(response, contract)
            return TransportResult(response.status, decoded, body_bytes)
    except OutboundError:
        raise
    except Exception as exc:
        raise _map_httpcore_error(exc) from exc
    finally:
        await pool.aclose()
