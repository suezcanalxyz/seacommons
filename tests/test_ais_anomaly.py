# SPDX-License-Identifier: AGPL-3.0-or-later
"""AIS anomaly detector, now fed from the shared AIS position hook."""
from __future__ import annotations

import time

import pytest

from core.anomaly import ais as ais_mod


@pytest.fixture
def detector(monkeypatch):
    added: list = []
    from core.intel import store as store_mod

    monkeypatch.setattr(store_mod.intel_store, "add", lambda e, dedup_key="": (added.append(e), True)[1])
    det = ais_mod.AISAnomalyDetector()
    det._running = True
    det._added = added
    return det


def test_impossible_speed_becomes_an_operator_only_intel_event(detector) -> None:
    detector._last_seen["247012345"] = {
        "lat": 35.0, "lon": 14.0, "ts": time.time() - 60, "speed": 10, "type": "", "name": "X",
    }
    detector.process_position("247012345", "X", 36.0, 15.0, 300.0, "")
    assert len(detector._added) == 1
    event = detector._added[0]
    assert event.type == "ais_anomaly"
    assert event.metadata["anomaly_type"] == "impossible_speed"
    assert event.metadata["is_distress"] is False
    assert event.metadata["publication_status"] == "internal"


def test_sdn_match_is_high_severity(detector) -> None:
    detector._sdn_mmsi = {"538001234"}
    detector.process_position("538001234", "SANCTIONED", 34.0, 18.0, 12.0, "")
    assert detector._added and detector._added[0].severity == "high"
    assert detector._added[0].metadata["anomaly_type"] == "sdn_match"


def test_emit_cooldown_prevents_a_flood(detector) -> None:
    detector._sdn_mmsi = {"538001234"}
    for _ in range(5):
        detector.process_position("538001234", "S", 34.0, 18.0, 12.0, "")
    assert len(detector._added) == 1


def test_dark_zone_entry_fires_once_on_crossing(detector) -> None:
    zone = ais_mod._DARK_ZONES[0]
    inside = ((zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2)
    detector.process_position("111", "V", zone[0] - 5, zone[1] - 5, 10.0, "")  # outside
    detector.process_position("111", "V", inside[0], inside[1], 10.0, "")      # inside
    kinds = {e.metadata["anomaly_type"] for e in detector._added}
    assert "dark_zone_entry" in kinds


def test_silence_sweep_emits_a_gap_for_a_vessel_gone_dark(detector) -> None:
    detector._last_seen["222"] = {
        "lat": 34.5, "lon": 18.0, "ts": time.time() - 1800,  # silent 30 min
        "speed": 12.0, "type": "", "name": "GHOST",
    }
    # run one sweep iteration inline
    now = time.time()
    for mmsi, seen in list(detector._last_seen.items()):
        silent_s = now - seen["ts"]
        if 900 < silent_s < 6 * 3600 and seen["speed"] >= 1.0 and not detector._in_dark_zone(seen["lat"], seen["lon"]):
            seen["gap_emitted"] = True
            detector._emit(ais_mod.AISAnomalyEvent(
                event_id="x", timestamp_utc="2026-08-27T00:00:00Z", anomaly_type="gap",
                mmsi=mmsi, vessel_name=seen["name"],
                position={"lat": seen["lat"], "lon": seen["lon"]},
                confidence=0.6, evidence={"silent_seconds": round(silent_s)},
            ))
    assert detector._added and detector._added[0].metadata["anomaly_type"] == "gap"


def test_position_hook_adapter_forwards_to_process_position(detector, monkeypatch) -> None:
    seen: list = []
    monkeypatch.setattr(detector, "process_position", lambda *a: seen.append(a))
    detector._on_feed_position("333", "NAME", 35.0, 14.0, 8.0, 0)
    assert seen == [("333", "NAME", 35.0, 14.0, 8.0, "")]
