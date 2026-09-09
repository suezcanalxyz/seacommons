# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Collection, Mapping
from urllib.parse import urljoin, urlsplit

from core.net.policy import (
    JSON_TEXT,
    OutboundError,
    ResponseContract,
    Resolver,
    TrustProfile,
    normalize_origin,
    resolve_target,
)
from core.net.transport import TimeoutBudget, TransportResult, async_send_pinned, send_pinned
from core.observability import record_outbound_request


@dataclass(frozen=True)
class OutboundResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes

    def json(self):
        try:
            return json.loads(self.body)
        except (TypeError, ValueError) as exc:
            raise OutboundError("upstream_error") from exc

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise OutboundError("upstream_error")


def _metric(profile: TrustProfile, method: str, outcome: str) -> None:
    record_outbound_request(policy=profile.value, method=method.upper(), outcome=outcome)


def _resolved(
    url: str,
    *,
    profile: TrustProfile,
    resolver: Resolver | None,
    allowed_origins: Collection[str] | None,
):
    if resolver is None:
        return resolve_target(
            url, profile=profile, allowed_origins=allowed_origins
        )
    return resolve_target(
        url,
        profile=profile,
        resolver=resolver,
        allowed_origins=allowed_origins,
    )


def _redirect_url(current: str, location: str) -> str:
    try:
        return urljoin(current, location)
    except ValueError as exc:
        raise OutboundError("redirect_blocked") from exc


def request(
    url: str,
    *,
    method: str = "GET",
    profile: TrustProfile = TrustProfile.PUBLIC_UNTRUSTED,
    contract: ResponseContract = JSON_TEXT,
    allowed_origins: Collection[str] | None = None,
    resolver: Resolver | None = None,
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    host_header: str | None = None,
    timeout: float | TimeoutBudget | None = None,
) -> OutboundResponse:
    method = method.upper()
    if profile == TrustProfile.PUBLIC_UNTRUSTED and method not in {"GET", "HEAD"}:
        _metric(profile, method, "invalid_request")
        raise OutboundError("invalid_request")

    current = url
    seen = {current}
    redirects = 0
    while True:
        try:
            target = _resolved(
                current,
                profile=profile,
                resolver=resolver,
                allowed_origins=allowed_origins,
            )
        except OutboundError as exc:
            outcome = exc.code if exc.code in {"blocked_target", "dns_failed", "invalid_scheme", "invalid_port"} else "invalid_request"
            _metric(profile, method, outcome)
            if redirects and profile == TrustProfile.PUBLIC_FIXED and exc.code == "blocked_target":
                raise OutboundError("redirect_blocked") from exc
            raise

        try:
            raw = send_pinned(
                target,
                current,
                method=method,
                contract=contract,
                headers=headers,
                body=body,
                host_header=host_header,
                timeout=timeout,
            )
        except OutboundError as exc:
            _metric(profile, method, exc.code)
            raise
        _metric(profile, method, "success")

        if not 300 <= raw.status_code < 400:
            return OutboundResponse(raw.status_code, raw.headers, raw.body)
        if profile == TrustProfile.OPERATOR_INTERNAL:
            raise OutboundError("redirect_blocked")
        if method not in {"GET", "HEAD"}:
            raise OutboundError("redirect_blocked")
        location = raw.headers.get("location")
        if not location:
            raise OutboundError("redirect_blocked")
        if redirects >= 3:
            raise OutboundError("redirect_limit")
        next_url = _redirect_url(current, location)
        if next_url in seen:
            raise OutboundError("redirect_limit")
        seen.add(next_url)
        current = next_url
        redirects += 1


async def async_request(
    url: str,
    *,
    method: str = "GET",
    profile: TrustProfile = TrustProfile.PUBLIC_UNTRUSTED,
    contract: ResponseContract = JSON_TEXT,
    allowed_origins: Collection[str] | None = None,
    resolver: Resolver | None = None,
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    host_header: str | None = None,
    timeout: float | TimeoutBudget | None = None,
) -> OutboundResponse:
    method = method.upper()
    if profile == TrustProfile.PUBLIC_UNTRUSTED and method not in {"GET", "HEAD"}:
        _metric(profile, method, "invalid_request")
        raise OutboundError("invalid_request")

    current = url
    seen = {current}
    redirects = 0
    while True:
        try:
            target = _resolved(
                current,
                profile=profile,
                resolver=resolver,
                allowed_origins=allowed_origins,
            )
        except OutboundError as exc:
            outcome = exc.code if exc.code in {"blocked_target", "dns_failed", "invalid_scheme", "invalid_port"} else "invalid_request"
            _metric(profile, method, outcome)
            if redirects and profile == TrustProfile.PUBLIC_FIXED and exc.code == "blocked_target":
                raise OutboundError("redirect_blocked") from exc
            raise

        try:
            raw = await async_send_pinned(
                target,
                current,
                method=method,
                contract=contract,
                headers=headers,
                body=body,
                host_header=host_header,
                timeout=timeout,
            )
        except OutboundError as exc:
            _metric(profile, method, exc.code)
            raise
        _metric(profile, method, "success")

        if not 300 <= raw.status_code < 400:
            return OutboundResponse(raw.status_code, raw.headers, raw.body)
        if profile == TrustProfile.OPERATOR_INTERNAL or method not in {"GET", "HEAD"}:
            raise OutboundError("redirect_blocked")
        location = raw.headers.get("location")
        if not location:
            raise OutboundError("redirect_blocked")
        if redirects >= 3:
            raise OutboundError("redirect_limit")
        next_url = _redirect_url(current, location)
        if next_url in seen:
            raise OutboundError("redirect_limit")
        seen.add(next_url)
        current = next_url
        redirects += 1


def _relative_url(base_url: str, relative: str) -> str:
    parsed = urlsplit(relative)
    if parsed.scheme or parsed.netloc:
        raise OutboundError("invalid_request")
    return f"{base_url.rstrip('/')}/{relative.lstrip('/')}"


class FixedOriginClient:
    def __init__(
        self,
        origins: Collection[str],
        *,
        timeout: float | TimeoutBudget | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        self._origins = tuple(origins)
        if not self._origins:
            raise OutboundError("invalid_request")
        for origin in self._origins:
            normalize_origin(origin)
        self._timeout = timeout
        self._resolver = resolver

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        contract: ResponseContract = JSON_TEXT,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> OutboundResponse:
        return request(
            url,
            method=method,
            profile=TrustProfile.PUBLIC_FIXED,
            contract=contract,
            allowed_origins=self._origins,
            resolver=self._resolver,
            headers=headers,
            body=body,
            timeout=self._timeout,
        )


class AsyncFixedOriginClient:
    def __init__(
        self,
        origins: Collection[str],
        *,
        timeout: float | TimeoutBudget | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        self._origins = tuple(origins)
        if not self._origins:
            raise OutboundError("invalid_request")
        for origin in self._origins:
            normalize_origin(origin)
        self._timeout = timeout
        self._resolver = resolver

    async def request(
        self,
        url: str,
        *,
        method: str = "GET",
        contract: ResponseContract = JSON_TEXT,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> OutboundResponse:
        return await async_request(
            url,
            method=method,
            profile=TrustProfile.PUBLIC_FIXED,
            contract=contract,
            allowed_origins=self._origins,
            resolver=self._resolver,
            headers=headers,
            body=body,
            timeout=self._timeout,
        )


class OperatorInternalClient:
    def __init__(
        self,
        origin: str,
        *,
        host_header: str | None = None,
        timeout: float | TimeoutBudget | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        parsed = urlsplit(origin)
        if parsed.username is not None or parsed.password is not None:
            raise OutboundError("invalid_request")
        normalized = normalize_origin(origin)
        if normalized.scheme not in {"http", "https"}:
            raise OutboundError("invalid_scheme")
        self._base_url = origin.rstrip("/")
        self._host_header = host_header
        self._timeout = timeout
        self._resolver = resolver

    def request(
        self,
        relative_path: str,
        *,
        method: str = "GET",
        contract: ResponseContract = JSON_TEXT,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> OutboundResponse:
        return request(
            _relative_url(self._base_url, relative_path),
            method=method,
            profile=TrustProfile.OPERATOR_INTERNAL,
            contract=contract,
            resolver=self._resolver,
            headers=headers,
            body=body,
            host_header=self._host_header,
            timeout=self._timeout,
        )


class AsyncOperatorInternalClient:
    def __init__(
        self,
        origin: str,
        *,
        host_header: str | None = None,
        timeout: float | TimeoutBudget | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        parsed = urlsplit(origin)
        if parsed.username is not None or parsed.password is not None:
            raise OutboundError("invalid_request")
        normalized = normalize_origin(origin)
        if normalized.scheme not in {"http", "https"}:
            raise OutboundError("invalid_scheme")
        self._base_url = origin.rstrip("/")
        self._host_header = host_header
        self._timeout = timeout
        self._resolver = resolver

    async def request(
        self,
        relative_path: str,
        *,
        method: str = "GET",
        contract: ResponseContract = JSON_TEXT,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> OutboundResponse:
        return await async_request(
            _relative_url(self._base_url, relative_path),
            method=method,
            profile=TrustProfile.OPERATOR_INTERNAL,
            contract=contract,
            resolver=self._resolver,
            headers=headers,
            body=body,
            host_header=self._host_header,
            timeout=self._timeout,
        )
