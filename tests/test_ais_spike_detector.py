# SPDX-License-Identifier: AGPL-3.0-or-later
"""AIS spike detector: circular search-pattern fit and the distress cross-check."""
from __future__ import annotations

import math
import os

os.environ["SEACOMMONS_TRACK_STORE_SYNC"] = "1"

from datetime import datetime, timezone

import pytest

from core.intel.ais_spike_detector import (
    AISSpikeDetector,
    _nearby_active_distress,
    _ngo_circular_pattern,
)
from core.intel.store import IntelEvent, intel_store
from core.vessels.track_store import track_store

_OCEAN_VIKING = "258479000"  # SOS Méditerranée -- real entry in ngo_registry


@pytest.fixture(autouse=True)
def _clean():
    with intel_store._lock:
        intel_store._events.clear()
        intel_store._seen.clear()
        intel_store._subscribers.clear()
    with track_store._buf_lock:
        track_store._buffer.clear()
    track_store._last.clear()
    track_store._last_write_epoch.clear()
    from core.db.models import VesselTrackDB
    from core.db.session import session_scope
    with session_scope() as db:
        db.query(VesselTrackDB).delete()
    yield


def _lay_ring(mmsi, center_lat=35.5, center_lon=12.6, radius_m=500, n=10, sog=3.0):
    for k in range(n):
        ang = k / n * 2 * math.pi
        dlat = radius_m * math.sin(ang) / 111_320
        dlon = radius_m * math.cos(ang) / (111_320 * math.cos(math.radians(center_lat)))
        track_store.on_position(mmsi, mmsi, center_lat + dlat, center_lon + dlon,
                                sog=sog, nav_status=0, received_at=datetime.now(timezone.utc))
        track_store._last_write_epoch[mmsi] = 0.0


def test_ngo_circular_pattern_needs_enough_fixes():
    _lay_ring(_OCEAN_VIKING, n=3)
    assert _ngo_circular_pattern(_OCEAN_VIKING) is None


def test_ngo_circular_pattern_detects_search_box():
    _lay_ring(_OCEAN_VIKING, n=10, radius_m=500)
    hit = _ngo_circular_pattern(_OCEAN_VIKING)
    assert hit is not None
    r_m, detail = hit
    assert 150 <= r_m <= 4000
    assert "ring radius" in detail


def test_ngo_circular_pattern_ignores_a_straight_line():
    for k in range(10):
        track_store.on_position(_OCEAN_VIKING, _OCEAN_VIKING, 35.5 + k * 0.01, 12.6,
                                sog=8.0, nav_status=0, received_at=datetime.now(timezone.utc))
        track_store._last_write_epoch[_OCEAN_VIKING] = 0.0
    assert _ngo_circular_pattern(_OCEAN_VIKING) is None


def test_nearby_active_distress_finds_within_radius():
    intel_store.add(IntelEvent(
        id="distress-1", type="distress", severity="critical",
        lat=35.5, lon=12.6, title="Distress report — ~40 people",
        source="alarm_phone", metadata={"is_distress": True, "incident_lifecycle": "active"},
    ))
    hit = _nearby_active_distress(35.55, 12.65)  # a few nm away
    assert hit is not None
    assert hit["case_id"] == "distress-1"


def test_nearby_active_distress_ignores_resolved_case():
    intel_store.add(IntelEvent(
        id="distress-2", type="distress", severity="critical",
        lat=35.5, lon=12.6, title="Distress report — resolved",
        source="alarm_phone", metadata={"is_distress": True, "incident_lifecycle": "resolved"},
    ))
    assert _nearby_active_distress(35.5, 12.6) is None


def test_nearby_active_distress_ignores_far_case():
    intel_store.add(IntelEvent(
        id="distress-3", type="distress", severity="critical",
        lat=10.0, lon=10.0, title="Distress report — far away",
        source="alarm_phone", metadata={"is_distress": True, "incident_lifecycle": "active"},
    ))
    assert _nearby_active_distress(35.5, 12.6) is None


def test_emit_rescue_cluster_flags_possible_response_near_active_distress():
    intel_store.add(IntelEvent(
        id="distress-4", type="distress", severity="critical",
        lat=35.5, lon=12.6, title="Distress report — ~40 people",
        source="alarm_phone", metadata={"is_distress": True, "incident_lifecycle": "active"},
    ))
    d = AISSpikeDetector()
    d._emit(
        spike_type="rescue_cluster", mmsi=_OCEAN_VIKING, name="Ocean Viking",
        lat=35.51, lon=12.61, severity="high", detail="Rescue cluster: 2 vessels within 3nm",
    )
    events = [e for e in intel_store.events(limit=10) if e.type == "ais_spike"]
    assert len(events) == 1
    ev = events[0]
    assert ev.severity == "critical"
    assert ev.metadata["possible_response_to"]["case_id"] == "distress-4"
    assert "possible response, not confirmed" in ev.text


def test_emit_rescue_cluster_without_nearby_distress_is_unflagged():
    d = AISSpikeDetector()
    d._emit(
        spike_type="rescue_cluster", mmsi=_OCEAN_VIKING, name="Ocean Viking",
        lat=35.51, lon=12.61, severity="high", detail="Rescue cluster: 2 vessels within 3nm",
    )
    ev = [e for e in intel_store.events(limit=10) if e.type == "ais_spike"][0]
    assert "possible_response_to" not in ev.metadata
    assert ev.severity == "high"


def test_emit_respects_cooldown_even_when_process_just_booted(monkeypatch):
    """Regression guard for the CI-only flake: a never-before-seen cooldown
    key must never be treated as "just emitted at t=0" -- that made the very
    first emission of any spike type vanish on a freshly booted process where
    time.monotonic() itself starts near zero (e.g. a fresh CI runner)."""
    import core.intel.ais_spike_detector as mod
    monkeypatch.setattr(mod.time, "monotonic", lambda: 12.0)  # < emit_cooldown_s
    d = AISSpikeDetector()
    d._emit(
        spike_type="rescue_cluster", mmsi=_OCEAN_VIKING, name="Ocean Viking",
        lat=35.51, lon=12.61, severity="high", detail="Rescue cluster: 2 vessels within 3nm",
    )
    assert len([e for e in intel_store.events(limit=10) if e.type == "ais_spike"]) == 1
