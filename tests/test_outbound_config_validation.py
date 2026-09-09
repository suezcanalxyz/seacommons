# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from scripts.validate_outbound_internal_config import validate_configured_origin


def test_success_output_never_exposes_host_port_path_or_query() -> None:
    lines: list[str] = []
    ok = validate_configured_origin(
        "API_INTERNAL_URL",
        "http://10.23.45.67:8100/private/path?token=super-secret",
        emit=lines.append,
    )
    assert ok is True
    assert lines == ["API_INTERNAL_URL valid http"]
    output = "\n".join(lines)
    for secret in ("10.23.45.67", "8100", "private", "super-secret"):
        assert secret not in output

def test_failure_output_never_exposes_host_or_exception_text() -> None:
    lines: list[str] = []
    ok = validate_configured_origin(
        "OIDC_JWKS",
        "ftp://private-jwks.internal:9443/certs?key=hidden",
        emit=lines.append,
    )
    assert ok is False
    assert lines == ["OIDC_JWKS invalid other"]
    output = "\n".join(lines)
    for secret in ("private-jwks.internal", "9443", "certs", "hidden", "invalid_scheme"):
        assert secret not in output


def test_empty_optional_setting_is_skipped_without_output() -> None:
    lines: list[str] = []
    assert validate_configured_origin(
        "DRIFT_WORKER_URL", "", emit=lines.append, optional=True
    ) is True
    assert lines == []
