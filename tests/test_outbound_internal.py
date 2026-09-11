# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from datetime import datetime, timezone

from core.config import config
from core.drift import engine as engine_module
from core.net.policy import OutboundError


def _drift_payload() -> dict:
    point = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [14.0, 35.0]}, "properties": {}}
    return {
        "trajectory": {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[14.0, 35.0]]}, "properties": {}},
        "cone_6h": point,
        "cone_12h": point,
        "cone_24h": point,
        "impact_point": None,
        "metadata": {"model": "test"},
    }


class _Response:
    status_code = 200

    def __init__(self, payload=None):
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def test_remote_drift_binds_operator_origin_and_preserves_secret(monkeypatch) -> None:
    captured = {}

    class _Client:
        def __init__(self, origin, **kwargs):
            captured["origin"] = origin
            captured["init"] = kwargs

        def request(self, path, **kwargs):
            captured["path"] = path
            captured["request"] = kwargs
            return _Response(_drift_payload())

    monkeypatch.setattr(engine_module, "OperatorInternalClient", _Client, raising=False)
    monkeypatch.setattr(config, "DRIFT_WORKER_URL", "http://10.0.0.5:9000")
    monkeypatch.setattr(config, "DRIFT_WORKER_SECRET", "worker-secret")
    monkeypatch.setattr(config, "DRIFT_WORKER_TIMEOUT_S", 90.0)

    result = engine_module._remote_compute(
        35.0, 14.0, datetime.now(timezone.utc), 6, "ocean_sar", {}, False
    )

    assert result is not None
    assert captured["origin"] == "http://10.0.0.5:9000"
    assert captured["path"] == "/compute"
    assert captured["init"]["timeout"] == 90.0
    headers = captured["request"]["headers"]
    assert headers["X-Worker-Secret"] == "worker-secret"
    body = json.loads(captured["request"]["body"])
    assert body["lat"] == 35.0
    assert body["lon"] == 14.0


def test_remote_drift_outbound_failure_keeps_in_process_fallback(monkeypatch) -> None:
    class _Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            raise OutboundError("redirect_blocked")

    monkeypatch.setattr(engine_module, "OperatorInternalClient", _Client, raising=False)
    monkeypatch.setattr(config, "DRIFT_WORKER_URL", "http://10.0.0.5:9000")
    monkeypatch.setattr(config, "DRIFT_WORKER_SECRET", "worker-secret")

    result = engine_module._remote_compute(
        35.0, 14.0, datetime.now(timezone.utc), 6, "ocean_sar", {}, False
    )
    assert result is None
