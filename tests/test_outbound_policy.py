# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import ipaddress

import pytest
from core.net.policy import (
    BINARY,
    IMAGE,
    JSON_TEXT,
    OutboundError,
    TrustProfile,
    normalize_origin,
    resolve_target,
)


def _resolver_for(*addresses: str):
    def _resolve(host: str, port: int) -> list[str]:
        assert host
        assert port > 0
        return list(addresses)

    return _resolve

@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://127.0.0.1/a", "invalid_scheme"),
        ("https://10.1.2.3/a", "blocked_target"),
        ("https://[::1]/a", "blocked_target"),
        ("https://169.254.169.254/latest/meta-data", "blocked_target"),
        ("https://user:pw@example.com/a", "blocked_target"),
        ("ftp://example.com/a", "invalid_scheme"),
        ("https://example.com:8443/a", "invalid_port"),
    ],
)
def test_public_untrusted_rejects_forbidden_destination_shapes(url: str, code: str) -> None:
    with pytest.raises(OutboundError) as exc:
        resolve_target(
            url,
            profile=TrustProfile.PUBLIC_UNTRUSTED,
            resolver=_resolver_for("93.184.216.34"),
        )
    assert exc.value.code == code


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1",
        "169.254.10.20", "224.0.0.1", "0.0.0.0", "240.0.0.1",
        "::1", "fe80::1", "ff02::1", "::", "fc00::1", "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
    ],
)
def test_public_untrusted_rejects_non_public_dns_answers(address: str) -> None:
    with pytest.raises(OutboundError) as exc:
        resolve_target(
            "https://example.com/image.png",
            profile=TrustProfile.PUBLIC_UNTRUSTED,
            resolver=_resolver_for(address),
        )
    assert exc.value.code == "blocked_target"

def test_public_target_blocks_when_any_dns_answer_is_forbidden() -> None:
    with pytest.raises(OutboundError) as exc:
        resolve_target(
            "https://example.com/a",
            profile=TrustProfile.PUBLIC_UNTRUSTED,
            resolver=_resolver_for("93.184.216.34", "10.0.0.9"),
        )
    assert exc.value.code == "blocked_target"


def test_public_target_fails_closed_on_dns_failure_or_empty_answers() -> None:
    def broken(_host: str, _port: int) -> list[str]:
        raise OSError("resolver detail must stay private")

    for resolver in (broken, _resolver_for()):
        with pytest.raises(OutboundError) as exc:
            resolve_target(
                "https://metadata.example/latest",
                profile=TrustProfile.PUBLIC_UNTRUSTED,
                resolver=resolver,
            )
        assert exc.value.code == "dns_failed"
        assert "metadata.example" not in str(exc.value)
        assert "resolver detail" not in str(exc.value)


def test_metadata_hostname_is_blocked_from_its_dns_answer() -> None:
    with pytest.raises(OutboundError) as exc:
        resolve_target(
            "https://metadata.google.internal/computeMetadata/v1/",
            profile=TrustProfile.PUBLIC_UNTRUSTED,
            resolver=_resolver_for("169.254.169.254"),
        )
    assert exc.value.code == "blocked_target"


def test_normalize_origin_applies_idna_terminal_dot_and_default_port() -> None:
    origin = normalize_origin("https://BÜCHER.example./path?q=secret")
    assert origin.scheme == "https"
    assert origin.host == "xn--bcher-kva.example"
    assert origin.port == 443
    assert origin.authority == "xn--bcher-kva.example"

def test_public_untrusted_returns_only_validated_public_addresses() -> None:
    target = resolve_target(
        "https://example.com/path",
        profile=TrustProfile.PUBLIC_UNTRUSTED,
        resolver=_resolver_for("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"),
    )
    assert target.origin.host == "example.com"
    assert target.origin.port == 443
    assert target.addresses == (
        ipaddress.ip_address("93.184.216.34"),
        ipaddress.ip_address("2606:2800:220:1:248:1893:25c8:1946"),
    )


def test_response_contracts_have_fixed_reviewed_caps() -> None:
    assert IMAGE.max_bytes == 8 * 1024 * 1024
    assert IMAGE.content_type_prefixes == ("image/",)
    assert JSON_TEXT.max_bytes == 16 * 1024 * 1024
    assert BINARY.max_bytes == 32 * 1024 * 1024
    assert max(IMAGE.max_bytes, JSON_TEXT.max_bytes, BINARY.max_bytes) == 32 * 1024 * 1024
