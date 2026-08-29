# SPDX-License-Identifier: AGPL-3.0-or-later
"""Chokepoint transit analytics over the AIS track store.

For each strategic strait (Bosphorus, Dardanelles, Kerch, Gibraltar, Sicilian
Channel, Suez, Bab el-Mandeb, Hormuz): how many distinct vessels transited in
the window, transit direction, median dwell, the AIS-off-during-transit rate
(shadow-fleet tell), and the flag mix. Replaces the naive bbox headcount in
`core/chokepoints/monitor.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def chokepoint_transits(hours: int = 24) -> dict[str, Any]:
    from core.mda.identity import mmsi_flag
    from core.mda.reference import reference
    from core.vessels.registry import registry
    from core.vessels.track_store import track_store

    now = datetime.now(timezone.utc)
    t0 = now - timedelta(hours=hours)
    cache = getattr(registry, "_cache", {}) or {}
    results = []
    for cp in reference.chokepoints():
        min_lon, min_lat, max_lon, max_lat = cp["bbox"]
        rows = track_store.positions_between(t0, now, bbox=(min_lon, min_lat, max_lon, max_lat))
        by_mmsi: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            by_mmsi.setdefault(r["mmsi"], []).append(r)

        north = south = east = west = 0
        dwell_min: list[float] = []
        went_dark = 0
        flags: dict[str, int] = {}
        for mmsi, pts in by_mmsi.items():
            pts.sort(key=lambda r: r["ts"])
            a, b = pts[0], pts[-1]
            if b["lat"] - a["lat"] > 0.03:
                north += 1
            elif a["lat"] - b["lat"] > 0.03:
                south += 1
            if b["lon"] - a["lon"] > 0.03:
                east += 1
            elif a["lon"] - b["lon"] > 0.03:
                west += 1
            span = (_p(b["ts"]) - _p(a["ts"])).total_seconds() / 60.0
            if 1 < span < hours * 60:
                dwell_min.append(span)
            # AIS-off-during-transit: a > 20-min hole between consecutive fixes
            for x, y in zip(pts, pts[1:]):
                if (_p(y["ts"]) - _p(x["ts"])).total_seconds() > 1200:
                    went_dark += 1
                    break
            v = cache.get(mmsi, {})
            fl = (v.get("flag") or mmsi_flag(mmsi) or "??")[:2].upper()
            flags[fl] = flags.get(fl, 0) + 1

        n = len(by_mmsi)
        dwell_min.sort()
        results.append({
            "id": cp["id"], "name": cp["name"],
            "center": [(min_lon + max_lon) / 2, (min_lat + max_lat) / 2],
            "vessels": n,
            "direction": {"north": north, "south": south, "east": east, "west": west},
            "median_dwell_min": round(dwell_min[len(dwell_min) // 2], 1) if dwell_min else None,
            "ais_off_during_transit": went_dark,
            "ais_off_rate": round(went_dark / n, 3) if n else 0.0,
            "flag_mix": dict(sorted(flags.items(), key=lambda kv: -kv[1])[:8]),
        })
    return {"window_hours": hours, "chokepoints": results,
            "generated_at": now.isoformat()}


def _p(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
