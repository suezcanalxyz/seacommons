# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json

from core.config import config
from core.intel.auto_drift_client import request_auto_drift


class _Response:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code


def _install_client(monkeypatch, captured: dict, *, status: int = 200, error=None):
    import core.intel.auto_drift_client as module

    class _Client:
        def __init__(self, origin, **kwargs):
            captured["origin"] = origin
            captured["init"] = kwargs

        def request(self, path, **kwargs):
            captured["path"] = path
            captured["request"] = kwargs
            if error is not None:
                raise error
            return _Response(status)

    monkeypatch.setattr(module, "OperatorInternalClient", _Client)


def test_sends_host_header_when_configured(monkeypatch):
    captured = {}
    _install_client(monkeypatch, captured)
    monkeypatch.setattr(config, "API_INTERNAL_URL", "http://10.0.0.5:80")
    monkeypatch.setattr(config, "API_INTERNAL_HOST_HEADER", "api.seacommons.org")

    assert request_auto_drift("evt-1", 35.0, 14.0) is True
    assert captured["origin"] == "http://10.0.0.5:80"
    assert captured["init"]["host_header"] == "api.seacommons.org"
    assert captured["path"] == "/api/v1/intel/auto-drift"


def test_no_host_header_when_not_configured(monkeypatch):
    captured = {}
    _install_client(monkeypatch, captured)
    monkeypatch.setattr(config, "API_INTERNAL_URL", "http://127.0.0.1:8100")
    monkeypatch.setattr(config, "API_INTERNAL_HOST_HEADER", "")

    assert request_auto_drift("evt-2", 35.0, 14.0) is True
    assert captured["init"]["host_header"] is None


def test_network_failure_is_swallowed_not_raised(monkeypatch):
    captured = {}
    _install_client(monkeypatch, captured, error=TimeoutError("connection timed out"))
    assert request_auto_drift("evt-3", 35.0, 14.0) is False


def test_auto_drift_binds_operator_origin_before_request_data(monkeypatch):
    captured = {}
    _install_client(monkeypatch, captured)
    monkeypatch.setattr(config, "API_INTERNAL_URL", "http://127.0.0.1:8100")
    monkeypatch.setattr(config, "API_INTERNAL_HOST_HEADER", "api.seacommons.org")

    hostile_id = "evt-https://evil.example/path"
    assert request_auto_drift(hostile_id, 35.0, 14.0) is True
    assert captured["origin"] == "http://127.0.0.1:8100"
    assert captured["path"] == "/api/v1/intel/auto-drift"
    assert captured["init"]["host_header"] == "api.seacommons.org"
    body = json.loads(captured["request"]["body"])
    assert body["intel_event_id"] == hostile_id
