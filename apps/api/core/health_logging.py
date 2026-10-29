# SPDX-License-Identifier: AGPL-3.0-or-later
"""Suppress only successful local health-probe access logs.

Keep health probes running at their existing cadence. Preserve all failed
requests, non-local requests, and normal API access logs for investigation.
A health monitor does not become less reliable just because its successes no
longer generate a journal event every second.
"""
from __future__ import annotations

import logging
import re

_LOCAL_SUCCESS = re.compile(
    r'^(?:127\.0\.0\.1|\[::1\]|::1):\d+ - '
    r'"GET /health HTTP/\d(?:\.\d)?" 200(?:\s|$)'
)


class SuccessfulLocalHealthAccessFilter(logging.Filter):
    """Drop only successful GET /health events from loopback Uvicorn access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno != logging.INFO:
            return True
        try:
            args = record.args
            if isinstance(args, tuple) and len(args) == 5:
                address, method, path, _http_version, status = args
                host = str(address).rsplit(":", 1)[0]
                if (
                    host in {"127.0.0.1", "::1", "[::1]"}
                    and method == "GET"
                    and path == "/health"
                    and int(status) == 200
                ):
                    return False
            return _LOCAL_SUCCESS.match(record.getMessage()) is None
        except (TypeError, ValueError, AttributeError):
            return True


class SuccessfulOriginHealthRequestFilter(logging.Filter):
    """Ignore only httpx's INFO success for the configured origin health URL."""

    def __init__(self, origin_health_url: str):
        super().__init__()
        self.origin_health_url = origin_health_url.strip()

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno != logging.INFO or not self.origin_health_url:
            return True
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            return True
        exact_prefix = (
            f'HTTP Request: GET {self.origin_health_url} "HTTP/'
        )
        return not (
            message.startswith(exact_prefix)
            and message.endswith(' 200 OK"')
        )
