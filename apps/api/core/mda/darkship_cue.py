# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drift-cued dark-ship search — the flagship cross-sensor product.

When a vessel goes dark (AIS gap) or spoofs, we know its last good position,
course and speed. From that we build a *reachable-area* polygon that grows with
time (kinematics widened by an ocean-current + wind allowance), then:

  1. check whether Global Fishing Watch has already published a Sentinel-1 SAR
     detection inside it (baseline coverage, free);
  2. query the Copernicus Sentinel-1 STAC for scenes that cover the area
     (recent acquisitions + an estimated next revisit);
  3. optionally (Phase 2 stretch) pull a cued GRD scene and run a light CFAR to
     find the unmatched bright target = the dark ship.

`build()` returns a dict attached to the alert / case. Everything is
best-effort — offline it still returns the ellipse and the revisit estimate.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Sentinel-1 (A+C) give roughly a 3-day effective revisit at Mediterranean
# latitudes counting ascending + descending passes.
_S1_REVISIT_HOURS = 72
_CURRENT_ALLOWANCE_KN = 1.5   # unknown set/drift while dark


def _dest_point(lat: float, lon: float, bearing_deg: float, dist_km: float) -> tuple[float, float]:
    r = 6371.0088
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    d = dist_km / r
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(br))
    lon2 = lon1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(lat1),
                             math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180


def reachable_polygon(lat: float, lon: float, course_deg: Optional[float],
                      speed_kn: Optional[float], hours: float) -> dict[str, Any]:
    """A teardrop reachable area: full circle of (max_speed*t) radius, biased
    forward along the last course. `course_deg`/`speed_kn` may be None."""
    hours = max(0.25, min(hours, 48.0))
    max_kn = max((speed_kn or 6.0) * 1.6, 12.0) + _CURRENT_ALLOWANCE_KN
    radius_km = max_kn * 1.852 * hours
    back_km = min(radius_km, (speed_kn or 3.0) * 1.852 * hours + 5.0)
    ring: list[list[float]] = []
    for deg in range(0, 360, 15):
        # forward semicircle uses the full radius, aft uses the smaller one
        if course_deg is not None:
            rel = abs(((deg - course_deg + 180) % 360) - 180)
            rr = radius_km if rel <= 90 else back_km + (radius_km - back_km) * (1 - (rel - 90) / 90)
        else:
            rr = radius_km
        p_lat, p_lon = _dest_point(lat, lon, deg, rr)
        ring.append([round(p_lon, 4), round(p_lat, 4)])
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring], "_radius_km": round(radius_km, 1)}


def _bbox_of(poly: dict[str, Any]) -> tuple[float, float, float, float]:
    xs = [c[0] for c in poly["coordinates"][0]]
    ys = [c[1] for c in poly["coordinates"][0]]
    return min(xs), min(ys), max(xs), max(ys)


def _recent_s1_scenes(bbox: tuple[float, float, float, float], since: datetime) -> list[dict[str, Any]]:
    try:
        import httpx

        body = {
            "collections": ["SENTINEL-1"],
            "bbox": list(bbox),
            "datetime": f"{since.isoformat()}/{datetime.now(timezone.utc).isoformat()}",
            "limit": 20,
        }
        r = httpx.post("https://catalogue.dataspace.copernicus.eu/stac/search",
                       json=body, timeout=45)
        r.raise_for_status()
        feats = r.json().get("features", [])
        out = []
        for f in feats:
            props = f.get("properties", {})
            if "GRD" not in str(props.get("productType", f.get("id", ""))):
                continue
            out.append({
                "id": f.get("id"),
                "acquired": props.get("datetime") or props.get("startTimeFromAscendingNode"),
                "orbit_direction": props.get("orbitDirection"),
                "footprint": f.get("geometry"),
            })
        return out
    except Exception as exc:
        logger.info("darkship_cue: S1 STAC query skipped: %s", exc)
        return []


def _gfw_sar_in_area(bbox: tuple[float, float, float, float], since: datetime) -> list[dict[str, Any]]:
    from core.config import config

    token = getattr(config, "GFW_API_TOKEN", "") or ""
    if not token:
        return []
    try:
        import httpx

        r = httpx.get(
            "https://gateway.api.globalfishingwatch.org/v3/datasets/"
            "public-global-sar-presence:latest/detections",
            params={"start-date": since.date().isoformat(),
                    "end-date": datetime.now(timezone.utc).date().isoformat(),
                    "bbox": ",".join(str(x) for x in bbox), "limit": 50},
            headers={"Authorization": f"Bearer {token}"}, timeout=45)
        r.raise_for_status()
        entries = r.json().get("entries", r.json().get("detections", []))
        return [{"lat": d.get("lat"), "lon": d.get("lon"), "matched": d.get("matched"),
                 "timestamp": d.get("timestamp")} for d in entries]
    except Exception as exc:
        logger.info("darkship_cue: GFW SAR query skipped: %s", exc)
        return []


def build(*, lat: float, lon: float, course_deg: Optional[float] = None,
          speed_kn: Optional[float] = None, gap_start: Optional[datetime] = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = gap_start or now
    hours = max(0.25, (now - start).total_seconds() / 3600.0)
    poly = reachable_polygon(lat, lon, course_deg, speed_kn, hours)
    bbox = _bbox_of(poly)
    since = start - timedelta(hours=2)

    s1 = _recent_s1_scenes(bbox, since)
    gfw = _gfw_sar_in_area(bbox, since)
    unmatched = [d for d in gfw if d.get("matched") is False]

    next_pass_h = _S1_REVISIT_HOURS
    if s1:
        try:
            last = max(datetime.fromisoformat(str(s["acquired"]).replace("Z", "+00:00"))
                       for s in s1 if s.get("acquired"))
            elapsed = (now - last).total_seconds() / 3600
            next_pass_h = max(0.0, _S1_REVISIT_HOURS - (elapsed % _S1_REVISIT_HOURS))
        except Exception:
            pass

    return {
        "generated_at": now.isoformat(),
        "last_known": {"lat": lat, "lon": lon, "course_deg": course_deg, "speed_kn": speed_kn},
        "dark_for_hours": round(hours, 1),
        "search_area": poly,
        "search_bbox": list(bbox),
        "radius_km": poly["_radius_km"],
        "sentinel1_scenes": s1,
        "gfw_sar_detections": gfw,
        "gfw_unmatched_in_area": unmatched,
        "next_s1_pass_estimate_hours": round(next_pass_h, 1),
        "recommendation": (
            "Unmatched SAR detection inside the search area — likely the dark vessel."
            if unmatched else
            f"No SAR detection yet. Next Sentinel-1 pass over the area in ~{round(next_pass_h)} h."
        ),
    }
