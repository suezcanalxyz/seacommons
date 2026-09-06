# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.vessels.ais_provider import (
    AISPositionObservation,
    AISProviderHealth,
    normalize_provider_name,
)

_NOW = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)


def test_position_observation_keeps_provider_and_station_provenance():
    obs = AISPositionObservation(
        mmsi="247123456", ship_name="TEST", lat=35.0, lon=15.0,
        sog=8.2, cog=91.0, heading=90.0, nav_status=0,
        observed_at=_NOW, received_at=_NOW,
        provider="aiscast", upstream_source="volunteer", station_id="station-42",
        source_terms="CC0-1.0", raw_message_id="abc",
    )
    assert obs.provider == "aiscast"
    assert obs.upstream_source == "volunteer"
    assert obs.station_id == "station-42"
    assert obs.source_terms == "CC0-1.0"
    assert obs.mmsi == "247123456"


def test_position_observation_is_immutable():
    obs = AISPositionObservation(
        mmsi="247123456", ship_name="", lat=35.0, lon=15.0,
        sog=None, cog=None, heading=None, nav_status=None,
        observed_at=_NOW, received_at=_NOW, provider="AISStream",
    )
    with pytest.raises(Exception):
        obs.lat = 36.0


def test_provider_name_is_normalized_without_losing_identity():
    assert normalize_provider_name(" AISStream ") == "aisstream"
    assert normalize_provider_name("Open Waters / aiscast") == "open_waters_aiscast"


def test_provider_health_preserves_last_message_and_error():
    health = AISProviderHealth(
        provider="aiscast", connected=False, last_message_at=_NOW,
        messages_received=12, error="timeout",
    )
    assert health.provider == "aiscast"
    assert health.error == "timeout"
