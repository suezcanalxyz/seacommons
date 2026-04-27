"""
VesselRegistry — persistent SQLite vessel database with in-memory cache.

Architecture:
  - SQLite stores one row per MMSI (upsert on every AIS message)
  - In-memory dict mirrors the DB for instant reads (no disk I/O on GET)
  - DB writes happen in a background thread (fire-and-forget, non-blocking)
  - GeoJSON is rebuilt lazily only when the cache is dirty
  - Incremental updates via ?since=<ISO timestamp> keep the frontend fast
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_DB_PATH = Path("core/data/vessels.db")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS vessels (
    mmsi          TEXT PRIMARY KEY,
    ship_name     TEXT,
    imo           TEXT,
    ship_type     INTEGER,
    flag          TEXT,
    ais_class     TEXT DEFAULT 'A',
    destination   TEXT,
    last_lat      REAL,
    last_lon      REAL,
    last_course   REAL,
    last_speed    REAL,
    last_heading  REAL,
    last_seen     TEXT,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_last_seen ON vessels(last_seen);
"""

_UPSERT_SQL = """
INSERT INTO vessels (
    mmsi, ship_name, imo, ship_type, flag, ais_class,
    destination, last_lat, last_lon, last_course,
    last_speed, last_heading, last_seen, updated_at
) VALUES (
    :mmsi, :ship_name, :imo, :ship_type, :flag, :ais_class,
    :destination, :last_lat, :last_lon, :last_course,
    :last_speed, :last_heading, :last_seen, :updated_at
)
ON CONFLICT(mmsi) DO UPDATE SET
    ship_name   = COALESCE(excluded.ship_name,   vessels.ship_name),
    imo         = COALESCE(excluded.imo,         vessels.imo),
    ship_type   = COALESCE(excluded.ship_type,   vessels.ship_type),
    flag        = COALESCE(excluded.flag,        vessels.flag),
    ais_class   = COALESCE(excluded.ais_class,   vessels.ais_class),
    destination = COALESCE(excluded.destination, vessels.destination),
    last_lat    = COALESCE(excluded.last_lat,    vessels.last_lat),
    last_lon    = COALESCE(excluded.last_lon,    vessels.last_lon),
    last_course = COALESCE(excluded.last_course, vessels.last_course),
    last_speed  = COALESCE(excluded.last_speed,  vessels.last_speed),
    last_heading= COALESCE(excluded.last_heading,vessels.last_heading),
    last_seen   = COALESCE(excluded.last_seen,   vessels.last_seen),
    updated_at  = excluded.updated_at;
"""


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class VesselRegistry:
    """Thread-safe vessel registry backed by SQLite with hot in-memory cache."""

    def __init__(self, db_path: Path = _DB_PATH):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cache: dict[str, dict] = {}
        self._dirty = False
        self._geojson_cache: dict | None = None
        self._write_queue: list[dict] = []
        self._write_lock = threading.Lock()
        self._init_db()
        self._load_cache()

    def _init_db(self) -> None:
        con = sqlite3.connect(self._db_path)
        con.executescript(_CREATE_SQL)
        con.commit()
        con.close()

    def _load_cache(self) -> None:
        """Load entire DB into memory at startup."""
        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM vessels").fetchall()
        con.close()
        with self._lock:
            self._cache = {r["mmsi"]: _row_to_dict(r) for r in rows}
            self._dirty = True  # force geojson rebuild on first call

    def upsert(
        self,
        mmsi: str,
        *,
        ship_name: str | None = None,
        imo: str | None = None,
        ship_type: int | None = None,
        flag: str | None = None,
        ais_class: str = "A",
        destination: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        course: float | None = None,
        speed: float | None = None,
        heading: float | None = None,
        last_seen: datetime | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        ts = (last_seen or datetime.now(timezone.utc)).isoformat()

        row: dict[str, Any] = {
            "mmsi": mmsi,
            "ship_name": ship_name,
            "imo": str(imo) if imo else None,
            "ship_type": ship_type,
            "flag": flag,
            "ais_class": ais_class,
            "destination": destination,
            "last_lat": lat,
            "last_lon": lon,
            "last_course": course,
            "last_speed": speed,
            "last_heading": heading,
            "last_seen": ts,
            "updated_at": now,
        }

        with self._lock:
            existing = self._cache.get(mmsi, {})
            merged: dict[str, Any] = {
                k: (row[k] if row[k] is not None else existing.get(k))
                for k in row
            }
            self._cache[mmsi] = merged
            self._dirty = True

        threading.Thread(target=self._db_write, args=(merged,), daemon=True).start()

    def _db_write(self, data: dict) -> None:
        try:
            con = sqlite3.connect(self._db_path, timeout=5)
            con.execute(_UPSERT_SQL, data)
            con.commit()
            con.close()
        except Exception:
            pass  # best-effort; cache is source of truth

    def get_geojson(self, since: str | None = None) -> dict:
        """
        Return GeoJSON FeatureCollection.
        If `since` is an ISO timestamp, only return vessels updated after that time.
        """
        with self._lock:
            if since:
                try:
                    cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    vessels = [
                        v for v in self._cache.values()
                        if v.get("last_seen") and
                           datetime.fromisoformat(v["last_seen"]) >= cutoff
                    ]
                except ValueError:
                    vessels = list(self._cache.values())
            else:
                if not self._dirty and self._geojson_cache is not None:
                    return self._geojson_cache
                vessels = list(self._cache.values())

        features = []
        for v in vessels:
            if v.get("last_lat") is None or v.get("last_lon") is None:
                continue
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [v["last_lon"], v["last_lat"]],
                },
                "properties": {
                    "vessel_id": v["mmsi"],
                    "mmsi": v["mmsi"],
                    "ship_name": v.get("ship_name") or v["mmsi"],
                    "imo": v.get("imo"),
                    "ship_type": v.get("ship_type"),
                    "ais_class": v.get("ais_class", "A"),
                    "destination": v.get("destination") or "",
                    "course": v.get("last_course"),
                    "speed": v.get("last_speed"),
                    "heading": v.get("last_heading"),
                    "last_seen": v.get("last_seen"),
                    "sources": ["aisstream"],
                },
            })

        result = {
            "type": "FeatureCollection",
            "features": features,
            "meta": {
                "total": len(features),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        if not since:
            with self._lock:
                self._geojson_cache = result
                self._dirty = False

        return result

    def stats(self) -> dict:
        with self._lock:
            total = len(self._cache)
            positioned = sum(
                1 for v in self._cache.values()
                if v.get("last_lat") is not None
            )
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            active = sum(
                1 for v in self._cache.values()
                if (v.get("last_seen") or "") >= cutoff
            )
        return {"total_known": total, "positioned": positioned, "active_30m": active}


# Module-level singleton — imported by AISStream client and API routes
registry = VesselRegistry()
