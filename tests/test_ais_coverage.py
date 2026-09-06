# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timezone

from core.vessels.ais_coverage import CoverageState, assess_coverage
from core.vessels.ais_provider import AISPositionObservation, AISProviderHealth

_NOW = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)


def test_single_provider_outage_blocks_vessel_specific_gap():
    c = assess_coverage(
        active_upstreams={"volunteer"}, degraded_upstreams={"aisstream"},
        nearby_traffic_seen=True,
    )
    assert c.status == "provider_degraded"
    assert "UPSTREAM_DEGRADED" in c.reason_codes
    assert c.gap_eligible is False


def test_healthy_upstreams_and_nearby_traffic_support_coverage_present():
    c = assess_coverage(
        active_upstreams={"aisstream", "volunteer"}, degraded_upstreams=set(),
        nearby_traffic_seen=True,
    )
    assert c.status == "coverage_present"
    assert c.gap_eligible is True


def test_aiscast_relay_of_aisstream_does_not_create_alternate_upstream():
    state = CoverageState()
    state.note_observation(AISPositionObservation(
        mmsi="247123456", ship_name="", lat=35.0, lon=15.0,
        sog=8.0, cog=90.0, heading=90.0, nav_status=0,
        observed_at=_NOW, received_at=_NOW,
        provider="aiscast", upstream_source="aisstream",
    ))
    state.update_health(AISProviderHealth(
        provider="aisstream", connected=False, last_message_at=None,
        messages_received=0, error="timeout",
    ))
    assessment = state.assess(nearby_traffic_seen=True, now=_NOW)
    assert assessment.active_upstreams == frozenset({"aisstream"})
    assert assessment.status == "provider_degraded"
    assert assessment.gap_eligible is False


def test_no_upstream_information_is_coverage_unknown():
    c = assess_coverage(active_upstreams=set(), degraded_upstreams=set(), nearby_traffic_seen=False)
    assert c.status == "coverage_unknown"
    assert c.gap_eligible is False
