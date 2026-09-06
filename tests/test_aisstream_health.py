# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import sys
import threading
import time
import types

from core.intel.source_registry import source_registry
from core.vessels.aisstream import AISStreamClient


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_repeated_connection_failure_reports_into_source_registry(monkeypatch):
    # Real bug this fixes: AIS never reported into the same health system
    # every other source uses, so a fully dead feed (connects, subscribes,
    # zero data every cycle -- the exact upstream AISstream failure mode)
    # went unnoticed for 7+ hours. This is the "connects but never gets
    # data" shape: recv() always raises (a timeout), never a connect()
    # failure, matching what was observed live.
    class _FakeWs:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def send(self, *a, **kw):
            pass
        def recv(self, timeout=None):
            raise TimeoutError("timed out in 60.0s")

    # websockets isn't installed in every dev environment this test suite
    # runs in (it's a server-only runtime dependency) -- inject a fake
    # module tree so `import websockets.sync.client as ws_sync` inside
    # _run() resolves without needing the real package.
    fake_client_module = types.ModuleType("websockets.sync.client")
    fake_client_module.connect = lambda *a, **kw: _FakeWs()
    fake_sync_module = types.ModuleType("websockets.sync")
    fake_sync_module.client = fake_client_module
    fake_websockets_module = types.ModuleType("websockets")
    fake_websockets_module.sync = fake_sync_module
    monkeypatch.setitem(sys.modules, "websockets", fake_websockets_module)
    monkeypatch.setitem(sys.modules, "websockets.sync", fake_sync_module)
    monkeypatch.setitem(sys.modules, "websockets.sync.client", fake_client_module)
    monkeypatch.setattr("core.vessels.aisstream.time.sleep", lambda s: None)

    client = AISStreamClient("dummy-key", label="Test Region")
    thread = threading.Thread(target=client._run, daemon=True)
    thread.start()
    try:
        source = None
        assert _wait_for(lambda: (
            source_registry.get("aisstream_test_region") is not None
            and source_registry.get("aisstream_test_region").consecutive_errors >= 2
        ))
        source = source_registry.get("aisstream_test_region")
        assert source.source_type == "ais"
        assert source.status in ("degraded", "offline")
        assert "timed out" in (source.last_error or "")
    finally:
        client.stop()


class _Registry:
    def __init__(self):
        self.rows = []

    def upsert(self, mmsi, **kwargs):
        self.rows.append((mmsi, kwargs))


def _position_message(mmsi="247123456", lat=35.1, lon=15.2):
    return {
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": mmsi, "ShipName": "TEST"},
        "Message": {"PositionReport": {
            "Latitude": lat, "Longitude": lon, "Sog": 7.2, "Cog": 91.0,
            "TrueHeading": 90, "NavigationalStatus": 0,
        }},
    }


def test_aisstream_position_report_emits_provider_observation():
    seen = []
    client = AISStreamClient("key", on_observation=seen.append)
    client._handle(_position_message(), _Registry())
    assert len(seen) == 1
    assert seen[0].provider == "aisstream"
    assert seen[0].upstream_source == "aisstream"
    assert seen[0].mmsi == "247123456"
