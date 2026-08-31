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
    from datetime import timedelta
    w = MdaWatch()
    # on the Greenstream corridor, near-stationary, 8 fixes over > 90 min
    for i in range(8):
        track_store.on_position("111000005", "SLOWSHIP", 35.80 + i * 0.0005, 14.10, sog=0.8,
                                nav_status=0, received_at=datetime.now(timezone.utc))
        track_store._last_write_epoch["111000005"] = 0.0
    from core.db.models import VesselTrackDB
    from core.db.session import session_scope
    with session_scope() as db:
        rows = db.query(VesselTrackDB).filter(VesselTrackDB.mmsi == "111000005").order_by(VesselTrackDB.ts).all()
        for k, r in enumerate(rows):
            r.ts = datetime.now(timezone.utc) - timedelta(minutes=130 - k * 15)
    assert w.scan_infra_loiter() == 1
    ev = _alerts("ais_anomaly")
    assert ev and ev[0].metadata["maritime_domain"] == "grey_zone"
    assert ev[0].metadata["infrastructure"]["kind"] == "pipeline"
    assert "not evidence of interference" in ev[0].metadata["detection_reason"]
    assert ev[0].url.endswith("mmsi:111000005")


def _loiter_in_malta_sts(mmsi: str, name: str) -> None:
    """8 near-stationary fixes over >90 min inside the bundled Malta
    bunkering/STS anchorage polygon (35.7-35.98N, 14.35-14.75E)."""
    from datetime import timedelta

    for i in range(8):
        track_store.on_position(mmsi, name, 35.85 + i * 0.0005, 14.55, sog=0.8,
                                nav_status=0, received_at=datetime.now(timezone.utc))
        track_store._last_write_epoch[mmsi] = 0.0
    from core.db.models import VesselTrackDB
    from core.db.session import session_scope
    with session_scope() as db:
        rows = db.query(VesselTrackDB).filter(VesselTrackDB.mmsi == mmsi).order_by(VesselTrackDB.ts).all()
        for k, r in enumerate(rows):
            r.ts = datetime.now(timezone.utc) - timedelta(minutes=130 - k * 15)


def test_infra_loiter_ignores_ordinary_vessel_in_sts_zone():
    """Idling in a bunkering/STS anchorage is what the zone is for -- not
    itself an anomaly for a vessel with no sanctions match."""
    from core.vessels.registry import registry

    w = MdaWatch()
    registry.upsert("111000020", ship_type=80, ship_name="ORDINARY TANKER")
    _loiter_in_malta_sts("111000020", "ORDINARY TANKER")
    assert w.scan_infra_loiter() == 0
    assert not _alerts("ais_anomaly")


def test_infra_loiter_flags_sanctioned_vessel_in_sts_zone():
    """A confirmed sanctions match idling at a known bunkering/STS hub is a
    classic evasion pattern -- surfaced even without a paired rendezvous
    vessel for scan_rendezvous to catch."""
    from core.db.models import SanctionedVesselDB
    from core.db.session import engine, session_scope
    from core.vessels.registry import registry

    SanctionedVesselDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.add(SanctionedVesselDB(source_list="OFAC_SDN", name="SHADOW TANKER",
                                  name_upper="SHADOW TANKER", imo=None, mmsi="111000021",
                                  program="RUSSIA-EO14024"))

    w = MdaWatch()
    registry.upsert("111000021", ship_type=80, ship_name="SHADOW TANKER")
    _loiter_in_malta_sts("111000021", "SHADOW TANKER")
    assert w.scan_infra_loiter() == 1
    ev = _alerts("ais_anomaly")
    assert ev[0].metadata["anomaly_type"] == "sanctions_bunkering_loiter"
    assert ev[0].metadata["maritime_domain"] == "sanctions"
    assert ev[0].metadata["sanctions_matched"] is True
    assert ev[0].metadata["infrastructure"]["kind"] == "sts_zone"


def test_gap_scan_flags_silent_vessel(monkeypatch):
    w = MdaWatch()
    _feed("111000006", 34.0, 20.0, sog=12.0)
    track_store._last["111000006"].ts = time.time() - 5400   # 90 min silent
    assert w.scan_gaps() == 1
    assert _alerts("ais_anomaly")[0].metadata["anomaly_type"] == "gap"


def test_gap_scan_ignores_pleasure_craft_at_anchor():
    """Ship_type 37 (pleasure craft) swinging AIS off at anchor near a marina
    is normal leisure behaviour, not a reporting anomaly -- must not alert
    unless the vessel is a confirmed sanctions match."""
    from core.vessels.registry import registry

    w = MdaWatch()
    registry.upsert("111000008", ship_type=37, ship_name="SUNSEEKER")
    _feed("111000008", 36.0, 14.5, sog=3.0)
    track_store._last["111000008"].ts = time.time() - 5400   # 90 min silent
    assert w.scan_gaps() == 0
    assert not _alerts("ais_anomaly")


def test_gap_scan_still_flags_sanctioned_pleasure_craft():
    """The same pleasure-craft exemption must not shield an actual sanctions
    match -- 'eliminate false positives, not sanctioned yachts'."""
    from core.db.models import SanctionedVesselDB
    from core.db.session import engine, session_scope
    from core.vessels.registry import registry

    SanctionedVesselDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.add(SanctionedVesselDB(source_list="OFAC_SDN", name="ROYAL STAR",
                                  name_upper="ROYAL STAR", imo=None, mmsi="111000009",
                                  program="RUSSIA-EO14024"))

    w = MdaWatch()
    registry.upsert("111000009", ship_type=37, ship_name="ROYAL STAR")
    _feed("111000009", 36.0, 14.5, sog=3.0)
    track_store._last["111000009"].ts = time.time() - 5400
    assert w.scan_gaps() == 1
    assert _alerts("ais_anomaly")[0].metadata["anomaly_type"] == "gap"


def test_gap_scan_ignores_passenger_ferry_near_port():
    """Ship_type 60 (passenger) going quiet at its own terminal (Piraeus) is
    the scheduled turnaround, not an anomaly."""
    from core.vessels.registry import registry

    w = MdaWatch()
    registry.upsert("111000014", ship_type=60, ship_name="BLUE STAR")
    _feed("111000014", 37.94, 23.60, sog=5.0)   # Piraeus
    track_store._last["111000014"].ts = time.time() - 5400
    assert w.scan_gaps() == 0
    assert not _alerts("ais_anomaly")


def test_gap_scan_ignores_passenger_ferry_in_open_water_too():
    """Passenger vessels are withheld from Live entirely for now (detection
    unchanged, not surfaced here) -- not just near a known port."""
    from core.vessels.registry import registry

    w = MdaWatch()
    registry.upsert("111000015", ship_type=60, ship_name="OPEN FERRY")
    _feed("111000015", 37.00, 18.00, sog=5.0)   # mid-Ionian, far from any bundled port
    track_store._last["111000015"].ts = time.time() - 5400
    assert w.scan_gaps() == 0
    assert not _alerts("ais_anomaly")


def test_gap_scan_still_flags_sanctioned_passenger_ferry_near_port():
    from core.db.models import SanctionedVesselDB
    from core.db.session import engine, session_scope
    from core.vessels.registry import registry

    SanctionedVesselDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.add(SanctionedVesselDB(source_list="OFAC_SDN", name="SHADOW FERRY",
                                  name_upper="SHADOW FERRY", imo=None, mmsi="111000016",
                                  program="RUSSIA-EO14024"))

    w = MdaWatch()
    registry.upsert("111000016", ship_type=60, ship_name="SHADOW FERRY")
    _feed("111000016", 37.94, 23.60, sog=5.0)   # Piraeus
    track_store._last["111000016"].ts = time.time() - 5400
    assert w.scan_gaps() == 1


def test_gap_scan_ignores_fishing_vessel():
    """Ship_type 30 (fishing) going dark far from any port is the vessel
    actually fishing -- scan_infra_loiter already exempts this ship_type
    blanket ('fishing vessels work slowly everywhere'); a gap gets the
    same treatment."""
    from core.vessels.registry import registry

    w = MdaWatch()
    registry.upsert("111000018", ship_type=30, ship_name="F/V LUCKY STAR")
    _feed("111000018", 37.00, 18.00, sog=4.0)   # open water, no port nearby
    track_store._last["111000018"].ts = time.time() - 5400
    assert w.scan_gaps() == 0
    assert not _alerts("ais_anomaly")


def test_gap_scan_still_flags_sanctioned_fishing_vessel():
    from core.db.models import SanctionedVesselDB
    from core.db.session import engine, session_scope
    from core.vessels.registry import registry

    SanctionedVesselDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.add(SanctionedVesselDB(source_list="OFAC_SDN", name="SHADOW TRAWLER",
                                  name_upper="SHADOW TRAWLER", imo=None, mmsi="111000019",
                                  program="RUSSIA-EO14024"))

    w = MdaWatch()
    registry.upsert("111000019", ship_type=30, ship_name="SHADOW TRAWLER")
    _feed("111000019", 37.00, 18.00, sog=4.0)
    track_store._last["111000019"].ts = time.time() - 5400
    assert w.scan_gaps() == 1


def test_spoofing_circular_track():
    import math
    w = MdaWatch()
    for k in range(14):
        ang = k / 14 * 2 * math.pi
        dlat = 200 * math.sin(ang) / 111320
        dlon = 200 * math.cos(ang) / (111320 * math.cos(math.radians(37)))
        track_store.on_position("111000010", "SPOOF", 37.0 + dlat, 15.0 + dlon,
                                sog=21.0, nav_status=0, received_at=datetime.now(timezone.utc))
        track_store._last_write_epoch["111000010"] = 0.0
    assert w.scan_spoofing() == 1
    ev = _alerts("ais_anomaly")
    assert ev[0].metadata["anomaly_type"] == "circle_spoof"


def test_spoofing_circular_ignores_pleasure_craft_swinging_at_anchor():
    """The same ring signature a real spoofer draws is what a boat swinging
    on its anchor chain near a marina produces -- must not alert a
    non-sanctioned pleasure craft on this signature alone."""
    import math

    from core.vessels.registry import registry

    w = MdaWatch()
    registry.upsert("111000012", ship_type=36, ship_name="WINDSWEPT")
    for k in range(14):
        ang = k / 14 * 2 * math.pi
        dlat = 200 * math.sin(ang) / 111320
        dlon = 200 * math.cos(ang) / (111320 * math.cos(math.radians(37)))
        track_store.on_position("111000012", "WINDSWEPT", 37.0 + dlat, 15.0 + dlon,
                                sog=0.4, nav_status=1, received_at=datetime.now(timezone.utc))
        track_store._last_write_epoch["111000012"] = 0.0
    assert w.scan_spoofing() == 0
    assert not _alerts("ais_anomaly")


def test_spoofing_circular_ignores_passenger_ferry_at_its_own_terminal():
    """A scheduled ferry's repeated berthing manoeuvre draws the same ring
    signature a spoofed track would -- passenger vessels are withheld from
    Live entirely for now (see the gap tests for the non-port case too)."""
    import math

    from core.vessels.registry import registry

    w = MdaWatch()
    registry.upsert("111000017", ship_type=60, ship_name="BLUE HORIZON")
    for k in range(14):
        ang = k / 14 * 2 * math.pi
        dlat = 200 * math.sin(ang) / 111320
        dlon = 200 * math.cos(ang) / (111320 * math.cos(math.radians(37.94)))
        track_store.on_position("111000017", "BLUE HORIZON", 37.94 + dlat, 23.60 + dlon,
                                sog=1.0, nav_status=0, received_at=datetime.now(timezone.utc))
        track_store._last_write_epoch["111000017"] = 0.0
    assert w.scan_spoofing() == 0
    assert not _alerts("ais_anomaly")


def test_spoofing_teleport():
    from datetime import timedelta
    w = MdaWatch()
    base = datetime.now(timezone.utc) - timedelta(minutes=15)
    for i in range(6):
        track_store.on_position("111000011", "JUMP", 35.0, 15.0, sog=10.0,
                                nav_status=0, received_at=base + timedelta(seconds=i * 20))
        track_store._last_write_epoch["111000011"] = 0.0
    # one impossible jump 40 s after the last fix
    track_store.on_position("111000011", "JUMP", 39.0, 20.0, sog=10.0,
                            nav_status=0, received_at=base + timedelta(seconds=6 * 20 + 40))
    track_store._last_write_epoch["111000011"] = 0.0
    assert w.scan_spoofing() == 1
    assert _alerts("ais_anomaly")[0].metadata["anomaly_type"] == "position_jump"


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
