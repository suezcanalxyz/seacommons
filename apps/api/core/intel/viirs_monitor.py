# SPDX-License-Identifier: AGPL-3.0-or-later
"""VIIRS Boat Detection ingest — lit vessels at night with no AIS.

The Earth Observation Group (Colorado School of Mines) publishes nightly
detections of lit boats from the VIIRS Day/Night Band. A VBD point with no AIS
vessel nearby is a dark-vessel / IUU candidate, especially inside an EEZ or MPA.

Public download is registration-gated and 45-days-delayed; a token
(`EOG_TOKEN`) unlocks near-real-time. Best-effort — a no-op without it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from core.config import config
from core.geo import haversine_km
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

_BBOX = {"min_lat": 28.0, "max_lat": 48.0, "min_lon": -8.0, "max_lon": 45.0}


def _record_source_observation(eid: str, row: dict, day: str, *, lat: float, lon: float) -> None:
    """docs/updates.md P0.2: a durable, lossless SourceObservation for
    every VIIRS detection this monitor receives -- before the existing
    intel_store.add() write path below. Best-effort and strictly
    additive: never raises into poll_once(), never alters what gets
    published."""
    try:
        from core.db.session import session_scope
        from core.intel.source_observation import record_observation

        with session_scope() as db:
            record_observation(
                db,
                service="maritime", lane="intelligence", observation_type="satellite_detection",
                source_name="VIIRS VBD", source_policy="official_api", source_id=eid,
                observed_at=f"{day}T01:30:00+00:00",
                raw_payload=str(row), lat=lat, lon=lon,
            )
    except Exception as exc:
        logger.debug("viirs_monitor: source_observation record skipped for %s: %s", eid, exc)


def poll_once() -> int:
    token = getattr(config, "EOG_TOKEN", "") or ""
    if not token:
        return 0
    try:
        import httpx

        day = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        r = httpx.get(
            "https://eogdata.mines.edu/wwwdata/viirs_products/vbd/v30/npp/csv/"
            f"VBD_npp_d{day.replace('-', '')}_global.csv",
            headers={"Authorization": f"Bearer {token}"}, timeout=90)
        r.raise_for_status()
        text = r.text
    except Exception as exc:
        logger.info("VIIRS poll skipped: %s", exc)
        return 0

    import csv
    import io

    from core.mda.reference import reference
    from core.vessels.registry import registry

    cache = getattr(registry, "_cache", {}) or {}
    ais_pts = [(v["last_lat"], v["last_lon"]) for v in cache.values()
               if v.get("last_lat") is not None]

    n = 0
    for row in csv.DictReader(io.StringIO(text)):
        try:
            lat = float(row.get("Lat_DNB") or row.get("lat"))
            lon = float(row.get("Lon_DNB") or row.get("lon"))
        except (TypeError, ValueError):
            continue
        if not (_BBOX["min_lat"] <= lat <= _BBOX["max_lat"]
                and _BBOX["min_lon"] <= lon <= _BBOX["max_lon"]):
            continue
        if any(haversine_km(lat, lon, a, b) < 2.0 for a, b in ais_pts):
            continue   # matched to a broadcasting vessel
        mpa = reference.in_mpa(lat, lon)
        eid = f"vbd:{row.get('id') or f'{lat:.4f}_{lon:.4f}_{day}'}"
        _record_source_observation(eid, row, day, lat=lat, lon=lon)
        added = intel_store.add(IntelEvent(
            id=eid, type="dark_candidate",
            severity="high" if mpa else "medium", lat=lat, lon=lon,
            title=f"VIIRS lit boat, no AIS{' — inside ' + mpa if mpa else ''}",
            text=(f"A lit vessel detected by VIIRS at night on {day} with no AIS "
                  f"vessel within 2 km" + (f", inside the {mpa} MPA." if mpa else ".")),
            source="VIIRS VBD", timestamp_utc=f"{day}T01:30:00+00:00",
            metadata={"anomaly_type": "dark_candidate", "maritime_domain": "iuu_fishing",
                      "is_distress": False, "publication_status": "internal",
                      "source_policy": "official_api", "coordinate_source": "viirs",
                      "mpa": mpa, "radiance": row.get("Rad_DNB")},
        ), dedup_key=eid)
        n += 1 if added else 0
    if n:
        logger.info("VIIRS: %d dark-candidate detections ingested", n)
    return n
