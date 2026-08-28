# SPDX-License-Identifier: AGPL-3.0-or-later
"""MDA periodic scans: rendezvous / STS, infra loitering, gap, identity."""
from __future__ import annotations

import os
import time

os.environ["SEACOMMONS_TRACK_STORE_SYNC"] = "1"

from datetime import datetime, timezone

import pytest

from core.intel.store import intel_store
from core.mda.watch import MdaWatch
from core.vessels.track_store import track_store


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


def _feed(mmsi, lat, lon, sog=0.5, secs_ago=0.0):
    ts = datetime.now(timezone.utc)
    track_store.on_position(mmsi, mmsi, lat, lon, sog=sog, nav_status=0, received_at=ts)
    # force the throttle clock so successive calls in a test all land
    track_store._last_write_epoch[mmsi] = 0.0


def _alerts(t):
    return [e for e in intel_store.events(limit=100) if e.type == t]


def test_rendezvous_emits_after_sustained(monkeypatch):
    w = MdaWatch()
    # two near-stationary vessels ~300 m apart, offshore (mid-Ionian)
    _feed("111000001", 37.00, 18.00, sog=0.3)
    _feed("111000002", 37.0025, 18.0005, sog=0.4)
    # first scan: pair seen, not yet sustained
    assert w.scan_rendezvous() == 0
    # backdate the pair's first_seen past the 30-min threshold
    key = tuple(sorted(("111000001", "111000002")))
    w._pairs[key]["first_seen"] = time.time() - 40 * 60
    _feed("111000001", 37.00, 18.00, sog=0.3)
    _feed("111000002", 37.0025, 18.0005, sog=0.4)
    assert w.scan_rendezvous() == 1
    ev = _alerts("ais_rendezvous")
    assert len(ev) == 1
    assert ev[0].metadata["maritime_domain"] == "sanctions"


def test_rendezvous_ignored_inside_a_port():
    w = MdaWatch()
    _feed("111000003", 37.94, 23.60, sog=0.2)   # Piraeus
    _feed("111000004", 37.941, 23.601, sog=0.2)
    key = tuple(sorted(("111000003", "111000004")))
    w._pairs[key] = {"first_seen": time.time() - 3600, "count": 5}
    assert w.scan_rendezvous() == 0


def test_infra_loiter_near_pipeline():
    w = MdaWatch()
    # on the Greenstream corridor, slow, several fixes over > 45 min
    for i in range(6):
        track_store.on_position("111000005", "SLOWSHIP", 35.80 + i * 0.001, 14.10, sog=1.5,
                                nav_status=0, received_at=datetime.now(timezone.utc))
        track_store._last_write_epoch["111000005"] = 0.0
    # widen the span by rewriting the earliest row's ts
    from core.db.models import VesselTrackDB
    from datetime import timedelta
    from core.db.session import session_scope
    with session_scope() as db:
        rows = db.query(VesselTrackDB).filter(VesselTrackDB.mmsi == "111000005").order_by(VesselTrackDB.ts).all()
        rows[0].ts = datetime.now(timezone.utc) - timedelta(minutes=60)
    assert w.scan_infra_loiter() == 1
    ev = _alerts("ais_anomaly")
    assert ev and ev[0].metadata["maritime_domain"] == "grey_zone"
    assert ev[0].metadata["infrastructure"]["kind"] == "pipeline"


def test_gap_scan_flags_silent_vessel(monkeypatch):
    w = MdaWatch()
    _feed("111000006", 34.0, 20.0, sog=12.0)
    track_store._last["111000006"].ts = time.time() - 5400   # 90 min silent
    assert w.scan_gaps() == 1
    assert _alerts("ais_anomaly")[0].metadata["anomaly_type"] == "gap"


def test_mmsi_duplicate():
    w = MdaWatch()
    # same MMSI, two clusters 300 km apart, many fixes
    for i in range(4):
        track_store.on_position("111000007", "CLONE", 35.0, 15.0, sog=8.0,
                                nav_status=0, received_at=datetime.now(timezone.utc))
        track_store._last_write_epoch["111000007"] = 0.0
        track_store.on_position("111000007", "CLONE", 40.0, 20.0, sog=8.0,
                                nav_status=0, received_at=datetime.now(timezone.utc))
        track_store._last_write_epoch["111000007"] = 0.0
    assert w.scan_mmsi_duplicate() == 1
    assert _alerts("vessel_identity")[0].metadata["anomaly_type"] == "mmsi_duplicate"
