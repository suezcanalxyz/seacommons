# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from core.vessels import ais_bus


def _fix():
    return SimpleNamespace(
        mmsi="247123456", ship_name="TEST", lat=35.0, lon=15.0,
        sog=8.2, nav_status=0, cog=91.0, heading=90.0,
        received_at=datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc),
    )


def setup_function():
    ais_bus._reset_for_tests()


def test_bus_delivers_exact_legacy_hook_shape():
    seen = []
    ais_bus.register_position_hook(lambda *args: seen.append(args))
    ais_bus.publish(_fix())
    assert len(seen) == 1
    assert len(seen[0]) == 9
    assert seen[0][0] == "247123456"
    assert seen[0][8] == _fix().received_at


def test_repeated_registration_is_idempotent():
    seen = []
    hook = lambda *args: seen.append(args)
    ais_bus.register_position_hook(hook)
    ais_bus.register_position_hook(hook)
    ais_bus.publish(_fix())
    assert len(seen) == 1
    assert ais_bus.position_hook_count() == 1


def test_broken_consumer_does_not_block_later_consumers():
    seen = []

    def broken(*_args):
        raise RuntimeError("boom")

    ais_bus.register_position_hook(broken)
    ais_bus.register_position_hook(lambda *args: seen.append(args))
    ais_bus.publish(_fix())
    assert len(seen) == 1
