# SPDX-License-Identifier: AGPL-3.0-or-later
"""Warfare / grey-zone context feeds for the MDA engine.

Two open sources, polled on an interval and turned into IntelEvents that the
fusion engine can correlate with a maritime incident:

  * ACLED  — armed-conflict events (naval / UAV / missile / air strike) in the
    AOI. `conflict_event` IntelEvent.  Needs ACLED_KEY (+ ACLED_EMAIL).
  * NGA MSI navigational warnings — in-force HYDROLANT / NAVAREA IV & XII plus
    the Med/Black Sea coordinators; parsed for firing exercises, missile tests,
    GNSS interference and UAV activity.  `navwarning` IntelEvent + a geofence
    used to *suppress* grey-zone false positives inside a declared zone.

`maritime_strike` in `core/intel/fusion.py` fires when a vessel incident is
corroborated by two of {navwarning, conflict_event, seismic event, jamming}.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from core.config import config
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

_AOI = {"min_lat": 28.0, "max_lat": 48.0, "min_lon": -8.0, "max_lon": 45.0}
_ZONE_FILE = Path(__file__).resolve().parents[1] / "data" / "reference" / "navwarn_zones.json"

_STRIKE_KW = re.compile(
    r"\b(missile|drone|uav|usv|unmanned|airstrike|air strike|shelling|struck|"
    r"attack|explosion|mine|torpedo|naval|kamikaze|loitering munition)\b", re.I)
_GNSS_KW = re.compile(r"\b(gps|gnss|jamming|spoofing|interference|navigation warning)\b", re.I)
_FIRING_KW = re.compile(r"\b(firing exercise|gunnery|live fire|missile (test|firing)|naval exercise)\b", re.I)


def _record_source_observation(
    *, source_name: str, source_id: str, observed_at: str, raw_payload: Any, lat: float, lon: float,
) -> None:
    """docs/updates.md P0.2: a durable, lossless SourceObservation for
    every ACLED/NGA MSI item this module polls -- before the existing
    intel_store.add() write path. Best-effort and strictly additive:
    never raises into poll_acled()/poll_navwarnings(), never alters what
    gets published."""
    try:
        from core.db.session import session_scope
        from core.intel.source_observation import record_observation

        with session_scope() as db:
            record_observation(
                db,
                service="maritime", lane="intelligence", observation_type="source_post",
                source_name=source_name, source_policy="official_rss", source_id=source_id,
                observed_at=observed_at, raw_payload=str(raw_payload), lat=lat, lon=lon,
            )
    except Exception as exc:
        logger.debug("warfare: source_observation record skipped for %s: %s", source_id, exc)


def _in_aoi(lat: float, lon: float) -> bool:
    return (_AOI["min_lat"] <= lat <= _AOI["max_lat"]
            and _AOI["min_lon"] <= lon <= _AOI["max_lon"])


# ── ACLED ───────────────────────────────────────────────────────────────────

def poll_acled() -> int:
    key = getattr(config, "ACLED_KEY", "")
    email = getattr(config, "ACLED_EMAIL", "") or getattr(config, "CMEMS_USERNAME", "")
    if not key:
        return 0
    try:
        import httpx

        since = (datetime.now(timezone.utc) - timedelta(days=14)).date().isoformat()
        url = ("https://api.acleddata.com/acled/read"
               f"?key={key}&email={email}&event_date={since}&event_date_where=%3E%3D"
               "&latitude_where=BETWEEN&latitude=28|48&longitude_where=BETWEEN&longitude=-8|45"
               "&limit=500")
        r = httpx.get(url, timeout=60)
        r.raise_for_status()
        data = r.json().get("data", [])
    except Exception as exc:
        logger.info("ACLED poll skipped: %s", exc)
        return 0

    n = 0
    for row in data:
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not _in_aoi(lat, lon):
            continue
        text = " ".join(str(row.get(k, "")) for k in
                        ("event_type", "sub_event_type", "notes", "actor1", "actor2"))
        maritime = "water" in text.lower() or "sea" in text.lower() or "naval" in text.lower() \
            or "port" in text.lower() or bool(_STRIKE_KW.search(text)) and lon > -8
        if not maritime:
            continue
        eid = f"acled:{row.get('data_id') or row.get('event_id_cnty')}"
        _record_source_observation(
            source_name="ACLED", source_id=eid,
            observed_at=(row.get("event_date") or "") + "T00:00:00+00:00",
            raw_payload=row, lat=lat, lon=lon,
        )
        added = intel_store.add(IntelEvent(
            id=eid, type="conflict_event",
            severity="high" if _STRIKE_KW.search(text) else "medium",
            lat=lat, lon=lon,
            title=f"ACLED: {row.get('sub_event_type') or row.get('event_type')} — {row.get('country')}",
            text=(row.get("notes") or "")[:600],
            url=row.get("source", "")[:200] if str(row.get("source", "")).startswith("http") else "",
            source="ACLED", timestamp_utc=(row.get("event_date") or "") + "T00:00:00+00:00",
            metadata={"anomaly_type": "conflict_event", "maritime_domain": "grey_zone",
                      "is_distress": False, "publication_status": "internal",
                      "source_policy": "official_rss", "coordinate_source": "acled",
                      "event_type": row.get("event_type"), "actors": [row.get("actor1"), row.get("actor2")]},
        ), dedup_key=eid)
        n += 1 if added else 0
    if n:
        logger.info("ACLED: %d maritime conflict events ingested", n)
    return n


# ── NGA navigational warnings ───────────────────────────────────────────────

def poll_navwarnings() -> int:
    try:
        import httpx

        # NGA MSI Broadcast Warnings (NAVAREA IV, XII, HYDROLANT, HYDROPAC ...)
        r = httpx.get("https://msi.nga.mil/api/publications/broadcast-warn"
                      "?status=active&output=json", timeout=60)
        r.raise_for_status()
        items = r.json().get("broadcast-warn", r.json()) if isinstance(r.json(), dict) else r.json()
    except Exception as exc:
        logger.info("navwarnings poll skipped: %s", exc)
        return 0

    zones: list[dict[str, Any]] = []
    n = 0
    for w in items if isinstance(items, list) else []:
        text = " ".join(str(w.get(k, "")) for k in ("text", "subject", "navArea", "msgYear", "msgNumber"))
        polys = _extract_positions(str(w.get("text", "")))
        if not polys:
            continue
        lat, lon = polys[0]
        if not _in_aoi(lat, lon):
            continue
        kind = ("gnss_interference" if _GNSS_KW.search(text)
                else "firing_exercise" if _FIRING_KW.search(text)
                else "strike_warning" if _STRIKE_KW.search(text)
                else None)
        if kind is None:
            continue
        wid = f"navwarn:{w.get('navArea')}:{w.get('msgYear')}:{w.get('msgNumber')}"
        zones.append({"kind": kind, "lat": lat, "lon": lon, "id": wid,
                      "points": polys, "text": str(w.get("text", ""))[:400]})
        _record_source_observation(
            source_name="NGA MSI", source_id=wid,
            observed_at=datetime.now(timezone.utc).isoformat(),
            raw_payload=w, lat=lat, lon=lon,
        )
        added = intel_store.add(IntelEvent(
            id=wid, type="navwarning",
            severity="high" if kind in ("strike_warning", "missile_test") else "medium",
            lat=lat, lon=lon,
            title=f"NAVWARN {w.get('navArea')} {w.get('msgNumber')}/{w.get('msgYear')} — {kind}",
            text=str(w.get("text", ""))[:600], source="NGA MSI",
            metadata={"anomaly_type": kind, "maritime_domain": "grey_zone",
                      "is_distress": False, "publication_status": "internal",
                      "source_policy": "official_api", "coordinate_source": "navtext",
                      "nav_area": w.get("navArea")},
        ), dedup_key=wid)
        n += 1 if added else 0

    try:
        _ZONE_FILE.write_text(json.dumps({"as_of": datetime.now(timezone.utc).isoformat(),
                                          "zones": zones}), encoding="utf-8")
        _zones.load()
    except Exception:
        pass
    if n:
        logger.info("navwarnings: %d relevant warnings ingested", n)
    return n


_POS_RE = re.compile(r"(\d{1,2})-(\d{2}(?:\.\d+)?)\s*([NS])\s+(\d{1,3})-(\d{2}(?:\.\d+)?)\s*([EW])")


def _extract_positions(text: str) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for d1, m1, hemi_lat, d2, m2, hemi_lon in _POS_RE.findall(text):
        lat = int(d1) + float(m1) / 60.0
        lon = int(d2) + float(m2) / 60.0
        if hemi_lat == "S":
            lat = -lat
        if hemi_lon == "W":
            lon = -lon
        out.append((round(lat, 4), round(lon, 4)))
    return out


class _NavwarnZones:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._zones: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(_ZONE_FILE.read_text(encoding="utf-8"))
            with self._lock:
                self._zones = data.get("zones", [])
        except Exception:
            with self._lock:
                self._zones = []

    def active_near(self, lat: float, lon: float, radius_km: float = 60.0) -> list[dict[str, Any]]:
        from core.geo import haversine_km
        with self._lock:
            zones = list(self._zones)
        return [z for z in zones
                if haversine_km(lat, lon, z["lat"], z["lon"]) <= radius_km]

    def suppresses_grey_zone(self, lat: float, lon: float) -> bool:
        """A declared firing / exercise zone explains a loiter / slow transit."""
        return any(z["kind"] == "firing_exercise"
                   for z in self.active_near(lat, lon, radius_km=40))


_zones = _NavwarnZones()


def navwarn_zones() -> _NavwarnZones:
    return _zones


# ── scheduler entry point ───────────────────────────────────────────────────

def poll_once() -> dict[str, int]:
    return {"acled": poll_acled(), "navwarnings": poll_navwarnings()}
