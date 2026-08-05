# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from core.config import config
from core.intel.auto_drift_client import request_auto_drift


def test_sends_host_header_when_configured(monkeypatch):
    monkeypatch.setattr(config, "API_INTERNAL_URL", "http://10.0.0.5:80")
    monkeypatch.setattr(config, "API_INTERNAL_HOST_HEADER", "api.seacommons.org")
    captured = {}

    class _FakeResponse:
        status_code = 200

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return _FakeResponse()

    monkeypatch.setattr("core.intel.auto_drift_client.httpx.post", fake_post)

    assert request_auto_drift("evt-1", 35.0, 14.0) is True
    assert captured["url"] == "http://10.0.0.5:80/api/v1/intel/auto-drift"
    assert captured["headers"] == {"Host": "api.seacommons.org"}


def test_no_host_header_when_not_configured(monkeypatch):
    monkeypatch.setattr(config, "API_INTERNAL_URL", "http://127.0.0.1:8100")
    monkeypatch.setattr(config, "API_INTERNAL_HOST_HEADER", "")
    captured = {}

    class _FakeResponse:
        status_code = 200

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["headers"] = headers
        return _FakeResponse()

    monkeypatch.setattr("core.intel.auto_drift_client.httpx.post", fake_post)

    assert request_auto_drift("evt-2", 35.0, 14.0) is True
    assert captured["headers"] == {}


def test_network_failure_is_swallowed_not_raised(monkeypatch):
    def fake_post(*args, **kwargs):
        raise TimeoutError("connection timed out")

    monkeypatch.setattr("core.intel.auto_drift_client.httpx.post", fake_post)

    assert request_auto_drift("evt-3", 35.0, 14.0) is False
