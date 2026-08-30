# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vessel incidents derived from the live AIS feed."""
from __future__ import annotations

import pytest

from core.intel import vessel_incident_monitor as vim


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def monitor(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(vim.time, "time", clock)
    added: list = []
    monkeypatch.setattr(vim.intel_store, "add", lambda event, dedup_key="": (added.append(event), True)[1])
    updated: list = []
    monkeypatch.setattr(
        vim.intel_store,
        "update_vessel_episode",
        lambda event_id, **kwargs: (updated.append((event_id, kwargs)), True)[1],
    )
    m = vim.VesselIncidentMonitor()
    m._running = True
    m._clock = clock  # test handle
    m._added = added  # test handle
    m._updated_calls = updated  # test handle
    return m


def test_sart_mmsi_emits_a_distress_immediately(monitor) -> None:
    monitor.on_position("972123456", "", 35.1, 14.2, 0.0, 0)
    assert len(monitor._added) == 1
    event = monitor._added[0]
    assert event.type == "distress"
    assert event.severity == "critical"
    assert event.metadata["is_distress"] is True
    assert event.metadata["publication_status"] == "published"
    assert event.linked_mmsi == "972123456"


def test_nav_status_14_is_treated_as_a_beacon(monitor) -> None:
    monitor.on_position("211456789", "MV TEST", 34.0, 13.0, 0.0, 14)
    assert monitor._added and monitor._added[0].metadata["ais_nav_status_kind"] == "distress_beacon"


def test_aground_emits_only_once_sustained(monitor) -> None:
    monitor.on_position("111222333", "CARGO A", 34.5, 12.5, 0.1, 6)
    assert monitor._added == []          # one report is not enough
    monitor._clock.advance(200)
    monitor.on_position("111222333", "CARGO A", 34.5, 12.5, 0.1, 6)
    assert len(monitor._added) == 1
    event = monitor._added[0]
    assert event.type == "distress"      # a grounding is operational
    assert event.metadata["ais_nav_status_kind"] == "aground"
    assert event.metadata["case_type"] == "vessel_incident"


def test_not_under_command_is_operator_review_not_auto_published(monitor) -> None:
    for _ in range(3):
        monitor.on_position("444555666", "TANKER B", 33.0, 15.0, 0.0, 2)
        monitor._clock.advance(400)
    assert len(monitor._added) == 1
    assert monitor._added[0].type == "vessel_incident"
    assert monitor._added[0].metadata["publication_status"] == "internal"
    assert monitor._added[0].metadata["is_distress"] is False
    assert monitor._added[0].metadata["maritime_domain"] == "grey_zone"
    assert monitor._added[0].metadata["drift_eligible"] is True


def test_restricted_manoeuvrability_is_ignored(monitor) -> None:
    for _ in range(6):
        monitor.on_position("777888999", "DREDGER", 32.0, 16.0, 2.0, 3)
        monitor._clock.advance(600)
    assert monitor._added == []


def test_returning_to_normal_status_resets_the_episode(monitor) -> None:
    monitor.on_position("101010101", "X", 34.0, 12.0, 0.1, 6)
    monitor._clock.advance(200)
    monitor.on_position("101010101", "X", 34.0, 12.0, 5.0, 0)   # under way again
    monitor._clock.advance(200)
    monitor.on_position("101010101", "X", 34.0, 12.0, 0.1, 6)   # aground once more
    assert monitor._added == []  # only one fresh report since the reset


def test_monitor_start_registers_exactly_one_position_hook(monkeypatch) -> None:
    from core.vessels import aisstream

    monkeypatch.setattr(aisstream, "_position_hooks", [])
    m = vim.VesselIncidentMonitor()
    m.start()
    m.start()  # idempotent
    assert aisstream.position_hook_count() == 1


def test_emit_cooldown_suppresses_a_repeat(monitor) -> None:
    monitor.on_position("202020202", "", 35.0, 14.0, 0.0, 6)
    monitor._clock.advance(200)
    monitor.on_position("202020202", "", 35.0, 14.0, 0.0, 6)
    assert len(monitor._added) == 1
    monitor._clock.advance(3600)          # still inside the 6 h cooldown
    monitor._episodes.clear()
    monitor.on_position("202020202", "", 35.0, 14.0, 0.0, 6)
    monitor._clock.advance(200)
    monitor.on_position("202020202", "", 35.0, 14.0, 0.0, 6)
    assert len(monitor._added) == 1      # not re-emitted


def test_sustained_incident_updates_the_same_episode_and_track(monitor) -> None:
    for _ in range(3):
        monitor.on_position("352001914", "ST. OLGA", 41.33, 29.14, 0.2, 2)
        monitor._clock.advance(400)
    assert len(monitor._added) == 1

    monitor._clock.advance(301)
    monitor.on_position("352001914", "ST. OLGA", 41.34, 29.16, 0.1, 2)

    assert len(monitor._added) == 1
    event_id, update = monitor._updated_calls[-1]
    assert event_id == "aisinc:352001914:not_under_command"
    assert (update["lat"], update["lon"]) == (41.34, 29.16)
    assert update["incident_lifecycle"] == "active"
