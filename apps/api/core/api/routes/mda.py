# SPDX-License-Identifier: AGPL-3.0-or-later
"""Maritime-domain-awareness / dark-vessel engine API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/mda", tags=["mda"])

_MDA_TYPES = {"ais_anomaly", "ais_rendezvous", "vessel_identity", "dark_candidate",
              "conflict_event", "navwarning", "correlated_alert"}


@router.get("/reference")
async def reference_geometry(kinds: str = Query(default="cable,pipeline,platform,sts_zone")):
    from core.mda.reference import reference

    want = {k.strip() for k in kinds.split(",") if k.strip()}
    return reference.to_geojson(kinds=want or None)


@router.get("/jamming")
async def jamming_zones():
    from core.mda.jamming import jamming

    return jamming.to_geojson()


def collect_mda_anomalies(hours: float, kind: str) -> dict:
    """Shared by both the authenticated operator route below and the public
    live-map projection (core/api/routes/live.py) — same data either way.
    Every field here is already public-interest (official sanctions-list
    hits, AIS-signal integrity flags derived from public broadcasts), so
    there is nothing to strip for the public projection; see live.py's
    docstring for the reasoning."""
    from core.intel.store import intel_store

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    candidates = []
    covered_ids: set[str] = set()
    for e in intel_store.events(limit=600):
        if e.type not in _MDA_TYPES:
            continue
        if (e.timestamp_utc or "") < cutoff:
            continue
        candidates.append(e)
        if e.type == "correlated_alert":
            covered_ids.update(e.metadata.get("contributing") or [])

    by_id = {c.id: c for c in candidates}
    out = []
    for e in candidates:
        if kind != "all" and e.type != kind:
            continue
        # A correlated_alert already represents its contributing raw
        # finding(s) with the same evidentiary content (same vessel, same
        # position) -- showing both as separate map points reads as a
        # duplicate. Keep only the richer correlated_alert when one exists.
        if e.type != "correlated_alert" and e.id in covered_ids:
            continue
        lat, lon = e.lat, e.lon
        if e.type == "correlated_alert" and (lat is None or lon is None):
            # A sanctions hit can correlate without a position (see
            # normalize() above); if a contributing raw event has since
            # picked up a real position, backfill it here rather than
            # plotting nothing.
            for cid in (e.metadata.get("contributing") or []):
                src = by_id.get(cid)
                if src is not None and src.lat is not None and src.lon is not None:
                    lat, lon = src.lat, src.lon
                    break
        out.append({
            "id": e.id, "type": e.type, "severity": e.severity,
            "lat": lat, "lon": lon, "title": e.title,
            "mmsi": e.linked_mmsi or None,
            "timestamp_utc": e.timestamp_utc,
            "anomaly_type": e.metadata.get("anomaly_type"),
            "maritime_domain": e.maritime_domain(),
            "metadata": {k: v for k, v in e.metadata.items()
                         if k in ("alert_type", "confidence", "contributing_sources",
                                  "tanker", "dark", "sts_zone", "jamming_score",
                                  "infrastructure", "identity", "darkship_cue",
                                  "spoof_reason", "case_id")},
        })
    out.sort(key=lambda x: str(x["timestamp_utc"]), reverse=True)
    return {"count": len(out), "anomalies": out}


@router.get("/anomalies")
async def anomalies(hours: int = Query(default=48, ge=1, le=720),
                    kind: str = Query(default="all")):
    return collect_mda_anomalies(hours, kind)


@router.get("/vessel/{mmsi}")
async def vessel_dossier(mmsi: str, hours: float = Query(default=72.0, ge=1, le=24 * 90)):
    from core.mda.identity import screen
    from core.vessels.registry import registry
    from core.vessels.track_store import track_store

    v = (getattr(registry, "_cache", {}) or {}).get(mmsi, {})
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    track = track_store.track(mmsi, since=since, limit=5000)
    return {
        "mmsi": mmsi,
        "static": {"name": v.get("ship_name"), "imo": v.get("imo"),
                   "ship_type": v.get("ship_type"), "flag": v.get("flag"),
                   "destination": v.get("destination"), "last_seen": v.get("last_seen")},
        "identity": screen(mmsi=mmsi, imo=v.get("imo"), name=v.get("ship_name") or "",
                           flag=v.get("flag") or ""),
        "track": {
            "type": "FeatureCollection",
            "features": ([{
                "type": "Feature",
                "geometry": {"type": "LineString",
                             "coordinates": [[p["lon"], p["lat"]] for p in track]},
                "properties": {"points": len(track)},
            }] if len(track) >= 2 else []),
        },
        "track_points": track,
    }


@router.get("/chokepoints")
async def chokepoint_transits(hours: int = Query(default=24, ge=1, le=168)):
    from core.mda.chokepoints import chokepoint_transits as _ct

    return _ct(hours=hours)


@router.get("/status")
async def mda_status():
    from core.db.models import SanctionedVesselDB
    from core.db.session import session_scope
    from core.mda.jamming import jamming
    from core.vessels.track_store import track_store

    try:
        with session_scope() as db:
            from sqlalchemy import func
            sanctioned = db.query(func.count(SanctionedVesselDB.id)).scalar() or 0
    except Exception:
        sanctioned = 0
    return {
        "track_store": track_store.stats(),
        "jamming_as_of": jamming.as_of(),
        "sanctioned_vessels": sanctioned,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
