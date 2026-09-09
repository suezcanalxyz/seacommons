# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Collection
from urllib.parse import urlsplit

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], list[str]]


class TrustProfile(StrEnum):
    PUBLIC_UNTRUSTED = "public_untrusted"
    PUBLIC_FIXED = "public_fixed"
    OPERATOR_INTERNAL = "operator_internal"


class OutboundError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class ResponseContract:
    name: str
    max_bytes: int
    content_type_prefixes: tuple[str, ...] = ()


IMAGE = ResponseContract("image", 8 * 1024 * 1024, ("image/",))
JSON_TEXT = ResponseContract("json_text", 16 * 1024 * 1024)
BINARY = ResponseContract("binary", 32 * 1024 * 1024)


@dataclass(frozen=True)
class NormalizedOrigin:
    scheme: str
    host: str
    port: int
    authority: str


@dataclass(frozen=True)
class ValidatedTarget:
    origin: NormalizedOrigin
    addresses: tuple[IPAddress, ...]


def _normalize_host(host: str) -> str:
    candidate = host.rstrip(".").lower()
    if not candidate:
        raise OutboundError("blocked_target")
    try:
        return candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise OutboundError("blocked_target") from exc


def normalize_origin(url: str) -> NormalizedOrigin:
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError as exc:
        raise OutboundError("invalid_port") from exc
    normalized_host = _normalize_host(host)
    if port is None:
        if scheme == "https":
            port = 443
        elif scheme == "http":
            port = 80
        else:
            port = 0
    display_host = f"[{normalized_host}]" if ":" in normalized_host else normalized_host
    default = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    authority = display_host if default else f"{display_host}:{port}"
    return NormalizedOrigin(scheme=scheme, host=normalized_host, port=port, authority=authority)


def _default_resolver(host: str, port: int) -> list[str]:
    try:
        rows = socket.getaddrinfo(host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise OutboundError("dns_failed") from exc
    answers: list[str] = []
    for row in rows:
        address = str(row[4][0])
        if address not in answers:
            answers.append(address)
    return answers


def _parse_ip(value: str) -> IPAddress:
    try:
        return ipaddress.ip_address(value)
    except ValueError as exc:
        raise OutboundError("dns_failed") from exc


def _is_public_routable(address: IPAddress) -> bool:
    classified: IPAddress = address
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        classified = address.ipv4_mapped
    return bool(
        classified.is_global
        and not classified.is_loopback
        and not classified.is_private
        and not classified.is_link_local
        and not classified.is_multicast
        and not classified.is_unspecified
        and not classified.is_reserved
    )


def _origin_key(origin: NormalizedOrigin) -> tuple[str, str, int]:
    return origin.scheme, origin.host, origin.port


def _allowed_origin_keys(origins: Collection[str | NormalizedOrigin] | None) -> set[tuple[str, str, int]]:
    if not origins:
        return set()
    keys: set[tuple[str, str, int]] = set()
    for item in origins:
        origin = item if isinstance(item, NormalizedOrigin) else normalize_origin(item)
        keys.add(_origin_key(origin))
    return keys


def resolve_target(
    url: str,
    *,
    profile: TrustProfile,
    resolver: Resolver = _default_resolver,
    allowed_origins: Collection[str | NormalizedOrigin] | None = None,
) -> ValidatedTarget:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise OutboundError("blocked_target") from exc
    if parsed.username is not None or parsed.password is not None:
        raise OutboundError("blocked_target")

    origin = normalize_origin(url)
    if profile in {TrustProfile.PUBLIC_UNTRUSTED, TrustProfile.PUBLIC_FIXED}:
        if origin.scheme != "https":
            raise OutboundError("invalid_scheme")
    elif origin.scheme not in {"http", "https"}:
        raise OutboundError("invalid_scheme")

    if profile == TrustProfile.PUBLIC_UNTRUSTED and origin.port != 443:
        raise OutboundError("invalid_port")
    if profile == TrustProfile.PUBLIC_FIXED:
        allowed = _allowed_origin_keys(allowed_origins)
        if not allowed or _origin_key(origin) not in allowed:
            raise OutboundError("blocked_target")

    try:
        literal = _parse_ip(origin.host)
    except OutboundError:
        literal = None

    if literal is not None:
        addresses = (literal,)
    else:
        try:
            raw_answers = resolver(origin.host, origin.port)
        except OutboundError:
            raise
        except Exception as exc:
            raise OutboundError("dns_failed") from exc
        if not raw_answers:
            raise OutboundError("dns_failed")
        addresses = tuple(_parse_ip(answer) for answer in raw_answers)

    if profile in {TrustProfile.PUBLIC_UNTRUSTED, TrustProfile.PUBLIC_FIXED}:
        if not addresses or any(not _is_public_routable(address) for address in addresses):
            raise OutboundError("blocked_target")

    return ValidatedTarget(origin=origin, addresses=addresses)
