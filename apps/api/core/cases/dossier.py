# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evidence dossier for a case — the traceable "why" behind an alert.

Every fusion-opened case links its contributing intel events
(`case_intel_events`). This renders that chain into one structured document:
the incident summary, a timeline of every contributing signal, the vessels
involved with their identity / sanctions screening and recent track, the
geographic context (nearest infrastructure, jurisdiction, jamming), any
drift-cued satellite search product, and a GeoJSON map layer.

Answers the "explainability" gap: an operator (or a regulator) can see exactly
which signals, in what order, produced the alert.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def build_dossier(case_id: str) -> Optional[dict[str, Any]]:
    from sqlalchemy import select

    from core.db.models import CaseDB, CaseIntelEventDB, CaseTimelineDB
    from core.db.session import session_scope

    with session_scope() as db:
        case = db.get(CaseDB, case_id)
        if case is None:
            return None
        links = db.execute(select(CaseIntelEventDB).where(
            CaseIntelEventDB.case_id == case_id)).scalars().all()
        event_ids = [ln.event_id for ln in links]
        timeline = db.execute(select(CaseTimelineDB).where(
            CaseTimelineDB.case_id == case_id).order_by(CaseTimelineDB.created_at)).scalars().all()
        case_row = {c.name: getattr(case, c.name) for c in case.__table__.columns}
        tl = [{"at": t.created_at.isoformat() if t.created_at else None,
               "type": t.event_type, "actor": t.actor, "body": t.body} for t in timeline]

    events = _resolve_events(event_ids)
    vessels = _vessel_sections({e.get("mmsi") for e in events if e.get("mmsi")})
    signal_timeline = sorted(
        [{"at": e.get("timestamp_utc"), "type": e["type"],
          "anomaly_type": e.get("anomaly_type"), "title": e.get("title"),
          "source": e.get("source"), "id": e["id"]} for e in events],
        key=lambda x: str(x["at"] or ""))

    context = _geo_context(case_row.get("lat"), case_row.get("lon"))
    cue = next((e["metadata"].get("darkship_cue") for e in events
                if e.get("metadata", {}).get("darkship_cue")), None)

    return {
        "case": case_row,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "incident": {
            "summary": case_row.get("summary"),
            "domain": case_row.get("case_type"),
            "position": [case_row.get("lon"), case_row.get("lat")]
            if case_row.get("lat") is not None else None,
        },
        "signal_timeline": signal_timeline,
        "case_timeline": tl,
        "contributing_events": events,
        "vessels": vessels,
        "geographic_context": context,
        "satellite_cue": cue,
        "map": _map_layer(events, vessels, case_row),
    }


def _resolve_events(event_ids: list[str]) -> list[dict[str, Any]]:
    from core.db.models import IntelEventDB
    from core.db.session import session_scope
    from core.intel.store import intel_store

    out: dict[str, dict[str, Any]] = {}
    for eid in event_ids:
        ev = intel_store.get(eid)
        if ev is not None:
            out[eid] = {"id": ev.id, "type": ev.type, "severity": ev.severity,
                        "title": ev.title, "text": ev.text, "lat": ev.lat, "lon": ev.lon,
                        "mmsi": ev.linked_mmsi or None, "timestamp_utc": ev.timestamp_utc,
                        "source": ev.source, "anomaly_type": ev.metadata.get("anomaly_type"),
                        "metadata": ev.metadata}
    missing = [e for e in event_ids if e not in out]
    if missing:
        with session_scope() as db:
            for row in db.query(IntelEventDB).filter(IntelEventDB.id.in_(missing)).all():
                meta = dict(row.meta or {})
                out[row.id] = {"id": row.id, "type": row.type, "severity": row.severity,
                               "title": row.title, "text": row.text, "lat": row.lat, "lon": row.lon,
                               "mmsi": row.linked_mmsi or None, "timestamp_utc": row.timestamp_utc,
                               "source": row.source, "anomaly_type": meta.get("anomaly_type"),
                               "metadata": meta}
    return [out[e] for e in event_ids if e in out]


def _vessel_sections(mmsis: set[str]) -> list[dict[str, Any]]:
    from core.mda.identity import screen
    from core.vessels.registry import registry
    from core.vessels.track_store import track_store

    cache = getattr(registry, "_cache", {}) or {}
    out = []
    for mmsi in sorted(m for m in mmsis if m):
        v = cache.get(mmsi, {})
        track = track_store.track(mmsi, limit=2000)
        out.append({
            "mmsi": mmsi,
            "name": v.get("ship_name"), "imo": v.get("imo"),
            "ship_type": v.get("ship_type"), "flag": v.get("flag"),
            "identity": screen(mmsi=mmsi, imo=v.get("imo"),
                               name=v.get("ship_name") or "", flag=v.get("flag") or ""),
            "track_points": len(track),
            "track": [[p["lon"], p["lat"]] for p in track],
        })
    return out


def _geo_context(lat: Optional[float], lon: Optional[float]) -> dict[str, Any]:
    if lat is None or lon is None:
        return {}
    try:
        from core.mda.jamming import jamming
        from core.mda.reference import reference

        hit = reference.nearest_infrastructure(lat, lon, max_km=50)
        port, port_km = reference.nearest_port_km(lat, lon)
        return {
            "nearest_infrastructure": ({"kind": hit.kind, "name": hit.name,
                                        "distance_km": hit.distance_km} if hit else None),
            "sts_zone": reference.in_sts_zone(lat, lon),
            "mpa": reference.in_mpa(lat, lon),
            "nearest_port": {"name": port, "distance_km": port_km},
            "chokepoint": reference.chokepoint_of(lat, lon),
            "jamming_score": jamming.in_jamming_zone(lat, lon),
        }
    except Exception:
        return {}


def _map_layer(events: list[dict[str, Any]], vessels: list[dict[str, Any]],
               case: dict[str, Any]) -> dict[str, Any]:
    feats: list[dict[str, Any]] = []
    if case.get("lat") is not None:
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [case["lon"], case["lat"]]},
                      "properties": {"role": "incident", "title": case.get("title")}})
    for e in events:
        if e.get("lat") is not None:
            feats.append({"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": [e["lon"], e["lat"]]},
                          "properties": {"role": "signal", "type": e["type"],
                                         "anomaly_type": e.get("anomaly_type"), "title": e["title"]}})
    for v in vessels:
        if len(v.get("track") or []) >= 2:
            feats.append({"type": "Feature",
                          "geometry": {"type": "LineString", "coordinates": v["track"]},
                          "properties": {"role": "track", "mmsi": v["mmsi"], "name": v.get("name")}})
    cue = next((e["metadata"].get("darkship_cue") for e in events
                if e.get("metadata", {}).get("darkship_cue")), None)
    if cue and cue.get("search_area"):
        feats.append({"type": "Feature", "geometry": cue["search_area"],
                      "properties": {"role": "search_area"}})
    return {"type": "FeatureCollection", "features": feats}
