# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from core.forensic import logger as forensic_logger
from core.net.policy import OutboundError


def _packet():
    return SimpleNamespace(model_dump=lambda: {"event_id": "evt-1", "payload": "safe"})


class _Response:
    def __init__(self, status_code: int = 204):
        self.status_code = status_code

    def raise_for_status(self):
        return None


def test_private_witness_uses_bound_operator_origin(monkeypatch) -> None:
    captured = {}

    class _Client:
        def __init__(self, origin, **kwargs):
            captured["origin"] = origin
            captured["init"] = kwargs

        def request(self, target, **kwargs):
            captured["target"] = target
            captured["request"] = kwargs
            return _Response()

    monkeypatch.setattr(forensic_logger, "OperatorInternalClient", _Client, raising=False)
    monkeypatch.setenv("WITNESS_ENDPOINTS", "http://127.0.0.1:9090/witness")

    forensic_logger._broadcast(_packet())

    assert captured["origin"] == "http://127.0.0.1:9090"
    assert captured["target"] == "/witness"
    assert captured["init"]["timeout"] == 5.0
    assert captured["request"]["method"] == "POST"
    body = json.loads(captured["request"]["body"])
    assert body["event_id"] == "evt-1"


def test_witness_fanout_continues_after_first_failure(monkeypatch) -> None:
    calls = []

    class _Client:
        def __init__(self, origin, **_kwargs):
            self.origin = origin

        def request(self, target, **_kwargs):
            calls.append((self.origin, target))
            if len(calls) == 1:
                raise OutboundError("timeout")
            return _Response()

    monkeypatch.setattr(forensic_logger, "OperatorInternalClient", _Client, raising=False)
    monkeypatch.setenv(
        "WITNESS_ENDPOINTS",
        '["http://10.0.0.5:9000/a","http://10.0.0.6:9000/b"]',
    )

    forensic_logger._broadcast(_packet())
    assert calls == [
        ("http://10.0.0.5:9000", "/a"),
        ("http://10.0.0.6:9000", "/b"),
    ]


def test_witness_logs_never_expose_endpoint_or_query_secret(monkeypatch, caplog) -> None:
    secret = "super-secret-witness-token"

    class _Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            raise OutboundError("redirect_blocked")

    monkeypatch.setattr(forensic_logger, "OperatorInternalClient", _Client, raising=False)
    monkeypatch.setenv(
        "WITNESS_ENDPOINTS",
        f"http://127.0.0.1:9090/witness?token={secret}",
    )

    with caplog.at_level(logging.INFO, logger=forensic_logger.__name__):
        forensic_logger._broadcast(_packet())

    assert secret not in caplog.text
    assert "127.0.0.1" not in caplog.text
    assert "redirect_blocked" in caplog.text
