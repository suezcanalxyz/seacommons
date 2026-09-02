# SPDX-License-Identifier: AGPL-3.0-or-later
"""VesselRegistry: nav_status persistence and GeoJSON projection."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from core.vessels.registry import VesselRegistry


def test_nav_status_round_trips_through_geojson(tmp_path):
    reg = VesselRegistry(db_path=tmp_path / "v.db")
    reg.upsert(
        "111000111", ship_name="Test", lat=35.0, lon=13.0,
        speed=0.2, course=90.0, nav_status=1,
        last_seen=datetime.now(timezone.utc),
    )
    feats = reg.get_geojson()["features"]
    assert feats and feats[0]["properties"]["nav_status"] == 1


def test_nav_status_is_coalesced_not_overwritten_by_a_later_position(tmp_path):
    reg = VesselRegistry(db_path=tmp_path / "v.db")
    now = datetime.now(timezone.utc)
    reg.upsert("111000222", lat=35.0, lon=13.0, nav_status=5, last_seen=now)
    # a later PositionReport with no NavigationalStatus must not wipe the last one
    reg.upsert("111000222", lat=35.1, lon=13.1, speed=0.0, last_seen=now)
    feats = {f["properties"]["mmsi"]: f for f in reg.get_geojson()["features"]}
    assert feats["111000222"]["properties"]["nav_status"] == 5


def test_added_column_migration_on_a_preexisting_db(tmp_path):
    db = tmp_path / "legacy.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE vessels (mmsi TEXT PRIMARY KEY, ship_name TEXT, "
        "last_lat REAL, last_lon REAL, last_speed REAL, last_course REAL, "
        "last_heading REAL, last_seen TEXT, updated_at TEXT);"
    )
    con.commit()
    con.close()
    reg = VesselRegistry(db_path=db)  # _init_db must ALTER in nav_status
    reg.upsert("111000333", lat=35.0, lon=13.0, nav_status=6,
               last_seen=datetime.now(timezone.utc))
    feats = reg.get_geojson()["features"]
    assert feats[0]["properties"]["nav_status"] == 6
