# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-episode NGO response analysis.

For a live distress episode, cross-check which known SAR NGO / coastguard
vessels (see ngo_registry.py) are present in the live AIS registry and whether
they are heading toward the episode. The analysis is computed on demand and is
stateless — it reads:

  * the live vessel registry snapshot (core/vessels/registry.py),
  * recent motion-pattern observations already emitted by the AIS spike
    detector (core/intel/ais_spike_detector.py) and stored in the intel store,
  * other public signals near the episode (cross-check / corroboration).

Exposed publicly through GET /api/v1/live/signals/{event_id}/response. The
module deliberately returns only AIS/NGO public telemetry — never raw source
messages or identifiers.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from core.intel.ngo_registry import get_ngo_info, is_ngo

logger = logging.getLogger(__name__)

# ── Tunables ──────────────────────────────────────────────────────────────────
MAX_RADIUS_NM = 250.0        # maximum analysis range around the episode
APPROACHING_WINDOW_DEG = 45.0  # course within this window of the bearing = heading toward
SPEED_SPIKE_KN = 18.0        # rescue sprint: above this, flag a speed spike
RELATED_SIGNAL_RADIUS_NM = 50.0  # cross-check radius for other live signals
SPIKE_LOOKBACK_HOURS = 6     # how far back to pull detector motion flags
_MIN_ETA_SPEED_KN = 1.0      # never divide by zero when computing ETA

# spike_type (from ais_spike_detector) → motion flag label shown in the UI
_SPIKE_FLAGS = {
    "ngo_search_pattern": "search_pattern",
    "sudden_stop": "sudden_stop",
    "vessel_loiter": "loitering",
    "rescue_cluster": "rescue_cluster",
}


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    R = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0.0, a)))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2 (degrees true)."""
    la1, lo1, la2, lo2 = map(math.radians, [lat1, lon1, lat2, lon2])
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = (math.cos(la1) * math.sin(la2)
         - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _bearing_delta(b1: float, b2: float) -> float:
    """Smallest angular difference between two bearings (0–180°)."""
    d = abs(b1 - b2) % 360
    return d if d <= 180 else 360 - d


def _parse_iso(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _recent_spike_flags(mmsi: str, now: datetime) -> list[str]:
    """Reuse the spike detector's stored observations for this MMSI."""
    try:
        from core.intel.store import intel_store
    except Exception:
        return []
    flags: list[str] = []
    for ev in intel_store.events(type_filter="ais_spike", limit=500, max_age_days=1):
        if str(ev.linked_mmsi or "") != str(mmsi):
            continue
        seen = _parse_iso(ev.timestamp_utc)
        if seen is None or (now - seen).total_seconds() / 3600 > SPIKE_LOOKBACK_HOURS:
            continue
        spike_type = str(ev.metadata.get("spike_type") or "")
        flag = _SPIKE_FLAGS.get(spike_type)
        if flag and flag not in flags:
            flags.append(flag)
    return flags


def _vessel_row(props: dict[str, Any], coords: list[Any],
                lat: float, lon: float, now: datetime) -> dict[str, Any]:
    """One NGO vessel's cross-check against the episode."""
    mmsi = str(props.get("mmsi") or "")
    name = str(props.get("ship_name") or mmsi or "Unknown")
    speed_kn = float(props.get("speed") if props.get("speed") is not None else props.get("sog") or 0)
    course_deg = float(props.get("course") if props.get("course") is not None else props.get("cog") or 0)
    v_lat = float(coords[1])
    v_lon = float(coords[0])

    distance_nm = _haversine_nm(lat, lon, v_lat, v_lon)
    bearing_to_episode = _bearing_deg(v_lat, v_lon, lat, lon)
    course_known = speed_kn > 0.1
    heading_toward = bool(
        course_known and _bearing_delta(course_deg, bearing_to_episode) <= APPROACHING_WINDOW_DEG
    )
    eta_h = distance_nm / max(speed_kn, _MIN_ETA_SPEED_KN) if speed_kn > 0.1 else None

    last_seen = str(props.get("last_seen") or props.get("timestamp_utc") or "")
    seen_dt = _parse_iso(last_seen)
    fix_age_min = round(max(0.0, (now - seen_dt).total_seconds() / 60)) if seen_dt else None

    info = get_ngo_info(mmsi) or {}

    motion_flags = _recent_spike_flags(mmsi, now)
    if speed_kn >= SPEED_SPIKE_KN and "speed_spike" not in motion_flags:
        motion_flags.insert(0, "speed_spike")

    return {
        "mmsi": mmsi,
        "name": name,
        "org": info.get("org", ""),
        "role": info.get("role", ""),
        "flag": info.get("flag", ""),
        "lat": v_lat,
        "lon": v_lon,
        "distance_nm": round(distance_nm, 2),
        "bearing_to_episode_deg": round(bearing_to_episode, 1),
        "course_deg": round(course_deg, 1) if course_known else None,
        "speed_kn": round(speed_kn, 1),
        "heading_toward": heading_toward,
        "eta_h": round(eta_h, 2) if eta_h is not None else None,
        "last_seen": last_seen,
        "fix_age_min": fix_age_min,
        "track_saved": f"AIS fix recorded {fix_age_min} min ago" if fix_age_min is not None else "no AIS fix",
        "motion_flags": motion_flags,
    }


def _build_geojson(episode_lat: float, episode_lon: float, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """GeoJSON for the map: episode→vessel lines + vessel points."""
    features: list[dict[str, Any]] = []
    for row in rows:
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [
                [episode_lon, episode_lat], [row["lon"], row["lat"]]
            ]},
            "properties": {
                "mmsi": row["mmsi"],
                "name": row["name"],
                "org": row["org"],
                "heading_toward": row["heading_toward"],
                "distance_nm": row["distance_nm"],
            },
        })
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {
                "mmsi": row["mmsi"],
                "name": row["name"],
                "org": row["org"],
                "heading_toward": row["heading_toward"],
                "distance_nm": row["distance_nm"],
                "eta_h": row["eta_h"],
                "speed_kn": row["speed_kn"],
            },
        })
    return {"type": "FeatureCollection", "features": features}


def analyze_ngo_response(
    event: Any,
    *,
    now: Optional[datetime] = None,
    registry_geojson: Optional[dict[str, Any]] = None,
    related_signals: Optional[list[Any]] = None,
) -> dict[str, Any]:
    """Compute the NGO cross-check for a positioned episode.

    Args:
        event: IntelEvent (or duck-typed) with `.lat`/`.lon`/`.title`/`.id`.
        now: wall clock override (tests).
        registry_geojson: optional pre-fetched registry snapshot; fetched lazily
            from core.vessels.registry otherwise.
        related_signals: other events to cross-check nearby; the caller is
            expected to pre-filter these to public, positioned signals.
    """
    lat = event.lat
    lon = event.lon
    if lat is None or lon is None:
        raise ValueError("episode has no position")
    now = now or datetime.now(timezone.utc)

    if registry_geojson is None:
        try:
            from core.vessels.registry import registry
            registry_geojson = registry.get_geojson()
        except Exception as exc:
            logger.warning("ngo_response: registry unavailable: %s", exc)
            registry_geojson = {"features": []}

    rows: list[dict[str, Any]] = []
    assets_within_50nm = 0
    ngo_within_50nm = 0
    for feature in registry_geojson.get("features", []):
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coords) != 2:
            continue
        props = feature.get("properties") or {}
        mmsi = str(props.get("mmsi") or "")
        if not mmsi:
            continue
        v_lat = float(coords[1])
        v_lon = float(coords[0])
        dist = _haversine_nm(lat, lon, v_lat, v_lon)
        if dist <= RELATED_SIGNAL_RADIUS_NM:
            assets_within_50nm += 1
        if not is_ngo(mmsi):
            continue
        if dist > MAX_RADIUS_NM:
            continue
        row = _vessel_row(props, coords, lat, lon, now)
        rows.append(row)
        if dist <= RELATED_SIGNAL_RADIUS_NM:
            ngo_within_50nm += 1

    rows.sort(key=lambda r: (not r["heading_toward"], r["distance_nm"]))

    # ── Cross-check: other live signals near this episode ─────────────────────
    related: list[dict[str, Any]] = []
    for other in (related_signals or []):
        other_id = getattr(other, "id", None)
        if not other_id or other_id == getattr(event, "id", None):
            continue
        if other.lat is None or other.lon is None:
            continue
        dist = _haversine_nm(lat, lon, other.lat, other.lon)
        if dist > RELATED_SIGNAL_RADIUS_NM:
            continue
        related.append({
            "id": other_id,
            "title": (getattr(other, "title", "") or "")[:120],
            "type": getattr(other, "type", ""),
            "distance_nm": round(dist, 2),
        })
    related.sort(key=lambda r: r["distance_nm"])

    approaching = [r for r in rows if r["heading_toward"]]
    nearest = min(rows, key=lambda r: r["distance_nm"]) if rows else None
    fastest = None
    for r in approaching:
        if r["eta_h"] is None:
            continue
        if fastest is None or r["eta_h"] < fastest["eta_h"]:
            fastest = r

    try:
        from core.intel import lifecycle
        state = lifecycle.distress_lifecycle(event, now=now, same_source=[])
    except Exception:
        state = str(event.metadata.get("incident_status") or "active") if getattr(event, "metadata", None) else "active"

    return {
        "episode": {
            "id": getattr(event, "id", ""),
            "title": (getattr(event, "title", "") or "")[:200],
            "lat": lat,
            "lon": lon,
            "lifecycle": state,
        },
        "generated_at": now.isoformat(),
        "summary": {
            "approaching_ngo_vessels": len(approaching),
            "ngo_vessels_in_range": len(rows),
            "nearest_ngo": {
                "name": nearest["name"],
                "org": nearest["org"],
                "distance_nm": nearest["distance_nm"],
            } if nearest else None,
            "fastest_approach_eta_h": fastest["eta_h"] if fastest else None,
            "fastest_approach_name": fastest["name"] if fastest else None,
            "assets_within_50nm": assets_within_50nm,
            "related_signals": len(related),
        },
        "ngo_vessels": rows,
        "cross_check": {
            "related_signals": related,
            "total_vessels_within_50nm": assets_within_50nm,
            "ngo_vessels_within_50nm": ngo_within_50nm,
        },
        "geojson": _build_geojson(lat, lon, rows),
    }
