# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.vessels.aiscast import AiscastClient, parse_aiscast_message

_NOW = datetime(2026, 9, 6, 10, 5, 2, tzinfo=timezone.utc)


def _event(**overrides):
    event = {
        "type": "event", "id": "15f3d254abc", "time": "2026-09-06T10:05:00Z",
        "mmsi": 247123456, "lat": 35.2, "lon": 15.3,
        "sog": 7.4, "cog": 182.0, "heading": 180, "nav_status": 0,
        "source": "volunteer", "station": "mt-01", "terms": "CC0-1.0",
    }
    event.update(overrides)
    return event


def test_aiscast_message_preserves_station_provenance():
    obs = parse_aiscast_message(_event(), received_at=_NOW)
    assert obs.provider == "aiscast"
    assert obs.upstream_source == "volunteer"
    assert obs.station_id == "mt-01"
    assert obs.source_terms == "CC0-1.0"
    assert obs.raw_message_id == "15f3d254abc"
    assert obs.mmsi == "247123456"


@pytest.mark.parametrize("payload", [
    _event(mmsi="bad"),
    _event(lat=None),
    _event(lon=None),
    _event(lat=91.0),
    _event(lon=181.0),
    {"type": "welcome", "limits": {"rate": 20}},
])
def test_invalid_or_non_event_frames_are_ignored(payload):
    assert parse_aiscast_message(payload, received_at=_NOW) is None


def test_missing_station_is_allowed():
    obs = parse_aiscast_message(_event(station=None), received_at=_NOW)
    assert obs is not None
    assert obs.station_id is None


def test_anonymous_subscription_is_bounded():
    client = AiscastClient(on_observation=lambda _obs: None, bbox=(32.0, 10.0, 38.0, 20.0))
    frame = client.subscription_frame()
    assert frame == {"type": "subscribe", "bbox": [[32.0, 10.0, 38.0, 20.0]]}


def test_health_starts_disconnected_and_zero_messages():
    client = AiscastClient(on_observation=lambda _obs: None, bbox=(32, 10, 38, 20))
    health = client.health()
    assert health.provider == "aiscast"
    assert health.connected is False
    assert health.messages_received == 0
