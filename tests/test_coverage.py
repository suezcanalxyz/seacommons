# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M4.2: AIS reception-quality CoverageBaseline."""
from __future__ import annotations

from datetime import datetime, timezone

from core.mda.coverage import compute_coverage_baseline


def test_dense_traffic_area_is_healthy_with_high_congestion(monkeypatch):
    import core.vessels.track_store as track_store_module

    own_rows = [{"mmsi": "111000111"}] * 6
    neighbour_rows = []
    for i in range(20):
        neighbour_mmsi = f"20000000{i}"
        neighbour_rows += [{"mmsi": neighbour_mmsi}] * 5
    monkeypatch.setattr(track_store_module.track_store, "track", lambda *a, **k: own_rows)
    monkeypatch.setattr(
        track_store_module.track_store, "positions_between",
        lambda *a, **k: own_rows + neighbour_rows,
    )
    monkeypatch.setattr("core.mda.jamming.jamming.in_jamming_zone", lambda *a, **k: 0.0)
    monkeypatch.setattr("core.intel.landmask.distance_to_coast_km", lambda *a, **k: 12.5)

    result = compute_coverage_baseline("111000111", 35.5, 14.1)
    assert result.source_health == "healthy"
    assert result.congestion == "high"
    assert result.local_receiver_density == 20
    assert result.preceding_track_density == 6
    assert result.coast_distance_km == 12.5
    assert result.jamming_context == 0.0


def test_no_nearby_traffic_at_all_is_unknown_not_a_guess(monkeypatch):
    import core.vessels.track_store as track_store_module

    monkeypatch.setattr(track_store_module.track_store, "track", lambda *a, **k: [])
    monkeypatch.setattr(track_store_module.track_store, "positions_between", lambda *a, **k: [])
    monkeypatch.setattr("core.mda.jamming.jamming.in_jamming_zone", lambda *a, **k: 0.0)
    monkeypatch.setattr("core.intel.landmask.distance_to_coast_km", lambda *a, **k: None)

    result = compute_coverage_baseline("111000222", 35.5, 14.1)
    assert result.source_health == "unknown"
    assert result.congestion == "unknown"
    assert result.local_receiver_density == 0
    assert result.neighbour_message_ratio is None


def test_neighbour_message_ratio_compares_against_the_local_median(monkeypatch):
    import core.vessels.track_store as track_store_module

    own_rows = [{"mmsi": "111000333"}] * 2  # this vessel reported half as often
    neighbour_rows = (
        [{"mmsi": "200000001"}] * 4
        + [{"mmsi": "200000002"}] * 4
        + [{"mmsi": "200000003"}] * 4
    )
    monkeypatch.setattr(track_store_module.track_store, "track", lambda *a, **k: own_rows)
    monkeypatch.setattr(
        track_store_module.track_store, "positions_between",
        lambda *a, **k: own_rows + neighbour_rows,
    )
    monkeypatch.setattr("core.mda.jamming.jamming.in_jamming_zone", lambda *a, **k: 0.1)
    monkeypatch.setattr("core.intel.landmask.distance_to_coast_km", lambda *a, **k: 5.0)

    result = compute_coverage_baseline("111000333", 35.5, 14.1)
    assert result.preceding_track_density == 2
    assert result.local_receiver_density == 3
    assert result.neighbour_message_ratio == 0.5  # 2 / median(4,4,4)


def test_never_raises_when_every_dependency_is_broken(monkeypatch):
    import core.vessels.track_store as track_store_module

    def _boom(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(track_store_module.track_store, "track", _boom)
    monkeypatch.setattr(track_store_module.track_store, "positions_between", _boom)
    monkeypatch.setattr("core.mda.jamming.jamming.in_jamming_zone", _boom)
    monkeypatch.setattr("core.intel.landmask.distance_to_coast_km", _boom)

    result = compute_coverage_baseline("111000444", 35.5, 14.1)
    assert result.source_health == "unknown"
    assert result.jamming_context is None
    assert result.coast_distance_km is None
    assert result.local_receiver_density == 0


def test_at_defaults_to_now_and_is_echoed_back():
    before = datetime.now(timezone.utc)
    result = compute_coverage_baseline("111000555", 35.5, 14.1)
    after = datetime.now(timezone.utc)
    assert before <= result.at <= after
