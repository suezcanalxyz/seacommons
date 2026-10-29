# SPDX-License-Identifier: AGPL-3.0-or-later
"""Successful health probes are quiet; failures and investigative logs remain."""
from __future__ import annotations

import logging

from core.health_logging import (
    SuccessfulLocalHealthAccessFilter,
    SuccessfulOriginHealthRequestFilter,
)


def _event(name: str, level: int, message: str, args=()):
    return logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1,
        msg=message, args=args, exc_info=None,
    )


def test_loopback_success_hidden_but_all_other_access_logs_retained():
    access_filter = SuccessfulLocalHealthAccessFilter()
    uvicorn_template = '%s - "%s %s HTTP/%s" %d'
    assert not access_filter.filter(
        _event(
            "uvicorn.access", logging.INFO, uvicorn_template,
            ("127.0.0.1:58716", "GET", "/health", "1.1", 200),
        )
    )
    # Formatted records must work even with Uvicorn's empty logger args.
    assert not access_filter.filter(
        _event("uvicorn.access", logging.INFO,
               '127.0.0.1:58716 - "GET /health HTTP/1.1" 200 OK')
    )
    assert access_filter.filter(
        _event(
            "uvicorn.access", logging.INFO, uvicorn_template,
            ("127.0.0.1:58716", "GET", "/health", "1.1", 503),
        )
    )
    assert access_filter.filter(
        _event(
            "uvicorn.access", logging.INFO, uvicorn_template,
            ("203.0.113.4:58716", "GET", "/health", "1.1", 200),
        )
    )
    assert access_filter.filter(
        _event(
            "uvicorn.access", logging.INFO, uvicorn_template,
            ("127.0.0.1:58716", "GET", "/ready", "1.1", 200),
        )
    )
    assert access_filter.filter(
        _event(
            "uvicorn.access", logging.INFO, uvicorn_template,
            ("127.0.0.1:58716", "GET", "/health?verbose=1", "1.1", 200),
        )
    )
    assert access_filter.filter(
        _event("uvicorn.access", logging.ERROR, 'database unavailable')
    )


def test_origin_request_filter_keeps_http_failures_other_requests_and_warnings():
    url = "http://127.0.0.1:8100/health"
    origin_filter = SuccessfulOriginHealthRequestFilter(url)
    assert not origin_filter.filter(
        _event("httpx", logging.INFO, f'HTTP Request: GET {url} "HTTP/1.1 200 OK"')
    )
    assert origin_filter.filter(
        _event("httpx", logging.INFO, f'HTTP Request: GET {url} "HTTP/1.1 503 Service Unavailable"')
    )
    assert origin_filter.filter(
        _event("httpx", logging.INFO, 'HTTP Request: POST https://edge.example/v1/live "HTTP/1.1 200 OK"')
    )
    assert origin_filter.filter(
        _event("httpx", logging.INFO, 'HTTP Request: GET http://127.0.0.1:8100/ready "HTTP/1.1 200 OK"')
    )
    assert origin_filter.filter(
        _event("httpx", logging.ERROR, f'HTTP Request: GET {url} "HTTP/1.1 200 OK"')
    )
    assert SuccessfulOriginHealthRequestFilter("").filter(
        _event("httpx", logging.INFO, f'HTTP Request: GET {url} "HTTP/1.1 200 OK"')
    )
