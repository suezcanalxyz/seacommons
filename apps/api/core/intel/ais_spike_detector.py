# SPDX-License-Identifier: AGPL-3.0-or-later
"""
AIS Spike Detector — identifies rescue operations and distress events
by analysing anomalous patterns in the live vessel registry.

Detection rules (all generate IntelEvents with type="ais_spike"):

  1. SUDDEN_STOP
     Vessel with last_speed > SPEED_THRESHOLD_KN drops to < STOP_THRESHOLD_KN
     while in open water (not inside a port bbox).
     Confidence boosted if position is within a known SAR hotspot.

  2. RESCUE_CLUSTER
     Two or more vessels converge within CLUSTER_RADIUS_NM of each other
     within the last CLUSTER_AGE_S seconds.  Confidence is 'high' if at
     least one vessel is a known NGO/coastguard.

  3. NGO_SEARCH_PATTERN
     A known NGO vessel shows erratic course changes (bearing delta > 60°
     between consecutive readings) at low speed (1–5 kn) — indicative of
     active search pattern.

  4. VESSEL_LOITER
     A vessel stops for > LOITER_MIN_S in open water near a known hotspot.
     Not applicable to anchored vessels (speed < 0.1 for > 6 h in same cell).

Runs in a background daemon thread; polls registry every POLL_INTERVAL_S.
State (previous speeds/courses/positions) kept in-memory.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from core.intel.ngo_registry import is_ngo, get_ngo_info, ngo_mmsi_set
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

# ── Tunable parameters ────────────────────────────────────────────────────────
POLL_INTERVAL_S    = 5 * 60     # scan every 5 minutes
SPEED_THRESHOLD_KN = 3.0        # vessel was "underway" above this speed
STOP_THRESHOLD_KN  = 0.4        # now considered stopped
CLUSTER_RADIUS_NM  = 3.0        # vessels this close = possible cluster
CLUSTER_AGE_S      = 30 * 60    # both readings must be this fresh
LOITER_MIN_S       = 45 * 60    # stopped > 45 min in open water = loiter
SEARCH_BEARING_DELTA = 60.0     # NGO course change > this = search pattern
SEARCH_SPEED_MAX_KN  = 5.0

# ── Circular search-pattern fit (track history, not just 2 samples) ──────────
# A genuine expanding-square / sector search box leaves the same geometric
# signature the AIS spoof detector flags (core.mda.watch._circle_fit): a
# tight, near-closed ring. Fitting the recent track catches a real search
# pattern the single-sample bearing-delta check above misses between polls;
# on a known NGO/coastguard hull the same signature reads as "searching",
# not "spoofed".
SEARCH_TRACK_WINDOW_MIN = 90
SEARCH_TRACK_MIN_FIXES  = 5
SEARCH_CIRCLE_MIN_M     = 150.0
SEARCH_CIRCLE_MAX_M     = 4000.0
SEARCH_CIRCLE_MAX_RESID = 0.20   # looser than the spoof detector's 0.12 --
                                  # a worked search box is not a perfect ring

# ── Cross-check against active humanitarian distress cases ───────────────────
# Context only -- never proof of an actual response. See
# core.live.vessel_episodes.add_nearby_humanitarian_context for the same
# non-causal "nearby, not confirmed" pattern applied to the public feed.
RESPONSE_CROSSCHECK_RADIUS_NM = 30.0
RESPONSE_CROSSCHECK_MAX_AGE_DAYS = 2
_DISTRESS_TYPES = frozenset({"distress", "iom_incident"})
_RESOLVED_LIFECYCLES = frozenset({"resolved", "archived"})
_RESCUE_RELEVANT_SPIKES = frozenset({"sudden_stop", "ngo_search_pattern", "rescue_cluster"})

# ── Known SAR hotspot zones (simple lat/lon/radius) ───────────────────────────
SAR_HOTSPOTS: list[dict[str, Any]] = [
    {"name": "Central Med / Lampedusa",   "lat": 35.50, "lon": 12.60, "radius_nm": 80},
    {"name": "Strait of Sicily",          "lat": 37.00, "lon": 11.50, "radius_nm": 90},
    {"name": "Zuwara departure zone",     "lat": 32.92, "lon": 12.08, "radius_nm": 60},
    {"name": "Libyan coast corridor",     "lat": 32.50, "lon": 14.00, "radius_nm": 120},
    {"name": "Tunisian coast SAR zone",   "lat": 33.90, "lon": 11.00, "radius_nm": 80},
    {"name": "Aegean / Lesvos",           "lat": 39.10, "lon": 26.55, "radius_nm": 50},
    {"name": "Aegean / Chios",            "lat": 38.37, "lon": 26.14, "radius_nm": 40},
    {"name": "Gulf of Aden",              "lat": 12.00, "lon": 47.00, "radius_nm": 200},
]

# ── Port exclusion zones (stop in port is not an anomaly) ────────────────────
PORT_ZONES: list[dict[str, Any]] = [
    {"lat": 35.50, "lon": 12.60, "radius_nm": 2,  "name": "Lampedusa port"},
    {"lat": 37.50, "lon": 15.09, "radius_nm": 3,  "name": "Catania port"},
    {"lat": 38.12, "lon": 13.35, "radius_nm": 4,  "name": "Palermo port"},
    {"lat": 35.90, "lon": 14.51, "radius_nm": 3,  "name": "Valletta port"},
    {"lat": 37.29, "lon": 13.53, "radius_nm": 2,  "name": "Porto Empedocle"},
    {"lat": 36.73, "lon": 14.85, "radius_nm": 2,  "name": "Pozzallo port"},
    {"lat": 32.90, "lon": 13.18, "radius_nm": 5,  "name": "Tripoli port"},
    {"lat": 34.74, "lon": 10.76, "radius_nm": 3,  "name": "Sfax port"},
    {"lat": 39.10, "lon": 26.55, "radius_nm": 3,  "name": "Mytilene port"},
    {"lat": 38.42, "lon": 27.14, "radius_nm": 5,  "name": "İzmir port"},
]


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


def _bearing_delta(b1: float, b2: float) -> float:
    """Smallest angular difference between two bearings (0–180°)."""
    d = abs(b1 - b2) % 360
    return d if d <= 180 else 360 - d


def _in_hotspot(lat: float, lon: float) -> Optional[str]:
    for hs in SAR_HOTSPOTS:
        if _haversine_nm(lat, lon, hs["lat"], hs["lon"]) <= hs["radius_nm"]:
            return hs["name"]
    return None


def _ngo_circular_pattern(mmsi: str) -> Optional[tuple[float, str]]:
    """Fit the vessel's last SEARCH_TRACK_WINDOW_MIN of track. Returns
    (radius_m, detail) when it looks like a worked search box (a tight,
    near-closed ring), else None."""
    try:
        from datetime import timedelta

        from core.mda.watch import _circle_fit
        from core.vessels.track_store import track_store

        pts = track_store.track(
            mmsi,
            since=datetime.now(timezone.utc) - timedelta(minutes=SEARCH_TRACK_WINDOW_MIN),
            limit=200,
        )
        if len(pts) < SEARCH_TRACK_MIN_FIXES:
            return None
        r_m, resid = _circle_fit([(p["lat"], p["lon"]) for p in pts])
        if r_m and SEARCH_CIRCLE_MIN_M <= r_m <= SEARCH_CIRCLE_MAX_M and resid < SEARCH_CIRCLE_MAX_RESID:
            return r_m, f"ring radius ~{r_m:.0f} m over {len(pts)} fixes in {SEARCH_TRACK_WINDOW_MIN} min"
    except Exception as exc:  # pragma: no cover
        logger.debug("_ngo_circular_pattern(%s) failed: %s", mmsi, exc)
    return None


def _nearby_active_distress(lat: float, lon: float) -> Optional[dict[str, Any]]:
    """Nearest ACTIVE distress/IOM-incident intel event within
    RESPONSE_CROSSCHECK_RADIUS_NM, or None. Context only -- proximity is never
    proof that a vessel is responding to it."""
    try:
        best: Optional[dict[str, Any]] = None
        for ev in intel_store.events(limit=300, max_age_days=RESPONSE_CROSSCHECK_MAX_AGE_DAYS):
            if ev.type not in _DISTRESS_TYPES and not ev.metadata.get("is_distress"):
                continue
            if str(ev.metadata.get("incident_lifecycle") or "active") in _RESOLVED_LIFECYCLES:
                continue
            if ev.lat is None or ev.lon is None:
                continue
            dist = _haversine_nm(lat, lon, ev.lat, ev.lon)
            if dist > RESPONSE_CROSSCHECK_RADIUS_NM:
                continue
            if best is None or dist < best["distance_nm"]:
                best = {"case_id": ev.id, "title": (ev.title or "")[:120], "distance_nm": round(dist, 1)}
        return best
    except Exception as exc:  # pragma: no cover
        logger.debug("_nearby_active_distress failed: %s", exc)
        return None


def _in_port(lat: float, lon: float) -> bool:
    for pz in PORT_ZONES:
        if _haversine_nm(lat, lon, pz["lat"], pz["lon"]) <= pz["radius_nm"]:
            return True
    return False


class AISSpikeDetector:
    """
    Scans the live VesselRegistry every POLL_INTERVAL_S seconds.
    Maintains minimal state (prev speed/course/position per MMSI).
    """

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # mmsi → {speed, course, lat, lon, ts, loiter_start}
        self._prev: dict[str, dict[str, Any]] = {}
        self._ngo_mmsis = ngo_mmsi_set()
        # Track already-emitted spikes to avoid storm of duplicates
        self._emitted: dict[str, float] = {}   # key → monotonic timestamp
        self._emit_cooldown_s = 30 * 60         # same spike re-emitted at most once per 30 min

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="intel-ais-spike"
        )
        self._thread.start()
        logger.info("AISSpikeDetector started (poll=%ds)", POLL_INTERVAL_S)

    def stop(self) -> None:
        self._running = False

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        # Wait for AIS data to accumulate
        time.sleep(60)
        while self._running:
            try:
                self._scan()
            except Exception as exc:
                logger.warning("AISSpikeDetector scan error: %s", exc)
            time.sleep(POLL_INTERVAL_S)

    def _scan(self) -> None:
        from core.vessels.registry import registry  # lazy to avoid circular import

        geojson = registry.get_geojson()
        features = geojson.get("features", [])
        if not features:
            return

        # Build current vessel snapshot
        vessels: list[dict[str, Any]] = []
        for feat in features:
            props = feat.get("properties") or {}
            coords = (feat.get("geometry") or {}).get("coordinates", [None, None])
            if not coords or coords[0] is None or coords[1] is None:
                continue
            v: dict[str, Any] = {
                "mmsi":        str(props.get("mmsi", "")),
                "name":        props.get("ship_name", ""),
                "lat":         float(coords[1]),
                "lon":         float(coords[0]),
                "speed":       float(props.get("last_speed", 0) or 0),
                "course":      float(props.get("last_course", 0) or 0),
                "last_seen":   str(props.get("last_seen", "")),
                "destination": str(props.get("destination", "") or ""),
            }
            vessels.append(v)

        now_mono = time.monotonic()

        # ── Rule 1: Sudden stop ────────────────────────────────────────────────
        for v in vessels:
            mmsi = v["mmsi"]
            prev = self._prev.get(mmsi)

            if prev:
                was_underway = prev["speed"] >= SPEED_THRESHOLD_KN
                now_stopped  = v["speed"] <= STOP_THRESHOLD_KN

                if was_underway and now_stopped:
                    if not _in_port(v["lat"], v["lon"]):
                        hotspot = _in_hotspot(v["lat"], v["lon"])
                        severity = "high" if hotspot else "medium"
                        if is_ngo(mmsi):
                            severity = "high"
                        self._emit(
                            spike_type="sudden_stop",
                            mmsi=mmsi,
                            name=v["name"],
                            lat=v["lat"],
                            lon=v["lon"],
                            severity=severity,
                            detail=(
                                f"Vessel {v['name'] or mmsi} stopped "
                                f"(was {prev['speed']:.1f} kn → {v['speed']:.1f} kn)"
                                + (f" in {hotspot}" if hotspot else "")
                            ),
                            ngo_info=get_ngo_info(mmsi),
                        )

                # Track loiter start
                if v["speed"] <= STOP_THRESHOLD_KN and not _in_port(v["lat"], v["lon"]):
                    if not prev.get("loiter_start"):
                        prev["loiter_start"] = now_mono
                    elif now_mono - prev["loiter_start"] >= LOITER_MIN_S:
                        hotspot = _in_hotspot(v["lat"], v["lon"])
                        if hotspot:
                            self._emit(
                                spike_type="vessel_loiter",
                                mmsi=mmsi,
                                name=v["name"],
                                lat=v["lat"],
                                lon=v["lon"],
                                severity="medium",
                                detail=(
                                    f"Vessel {v['name'] or mmsi} loitering "
                                    f"{(now_mono - prev['loiter_start'])/60:.0f} min "
                                    f"in {hotspot}"
                                ),
                                ngo_info=get_ngo_info(mmsi),
                            )
                elif "loiter_start" in prev:
                    del prev["loiter_start"]

                # ── Rule 3: NGO search pattern ─────────────────────────────────
                if is_ngo(mmsi):
                    delta = _bearing_delta(prev["course"], v["course"])
                    zigzag = (delta >= SEARCH_BEARING_DELTA
                              and STOP_THRESHOLD_KN < v["speed"] <= SEARCH_SPEED_MAX_KN)
                    # The 2-sample bearing check above only ever sees the two
                    # most recent 5-min polls -- too coarse to catch a real
                    # search box unfolding between them. Fit the actual track.
                    circular = (
                        _ngo_circular_pattern(mmsi)
                        if STOP_THRESHOLD_KN < v["speed"] <= SEARCH_SPEED_MAX_KN else None
                    )
                    if zigzag or circular:
                        detail = (
                            f"{v['name'] or mmsi} ({get_ngo_info(mmsi)['org']}) "
                            f"executing search pattern"
                        )
                        if circular:
                            detail += f" — {circular[1]}"
                        elif zigzag:
                            detail += f" — bearing Δ {delta:.0f}° at {v['speed']:.1f} kn"
                        self._emit(
                            spike_type="ngo_search_pattern",
                            mmsi=mmsi,
                            name=v["name"],
                            lat=v["lat"],
                            lon=v["lon"],
                            severity="high",
                            detail=detail,
                            ngo_info=get_ngo_info(mmsi),
                            metadata={"pattern": "circular" if circular else "course_change"},
                        )

            # Update state
            self._prev[mmsi] = {
                "speed":  v["speed"],
                "course": v["course"],
                "lat":    v["lat"],
                "lon":    v["lon"],
                "loiter_start": self._prev.get(mmsi, {}).get("loiter_start"),
            }

        # ── Rule 2: Rescue cluster ────────────────────────────────────────────
        self._check_clusters(vessels)

        # Prune stale spike cooldowns
        cutoff = now_mono - self._emit_cooldown_s
        self._emitted = {k: v for k, v in self._emitted.items() if v > cutoff}

    def _check_clusters(self, vessels: list[dict[str, Any]]) -> None:
        """Find groups of 2+ vessels within CLUSTER_RADIUS_NM."""
        positioned = [v for v in vessels if v.get("lat") and v.get("lon")]
        ngo_in_group: set[str] = set()

        for i, v1 in enumerate(positioned):
            nearby = []
            for j, v2 in enumerate(positioned):
                if i >= j:
                    continue
                dist = _haversine_nm(v1["lat"], v1["lon"], v2["lat"], v2["lon"])
                if dist <= CLUSTER_RADIUS_NM:
                    nearby.append((v2, dist))

            if not nearby:
                continue

            group = [v1] + [v for v, _ in nearby]
            ngo_vessels = [v for v in group if is_ngo(v["mmsi"])]
            if not ngo_vessels:
                continue  # only flag clusters that include known NGO/CG vessels

            hotspot = _in_hotspot(v1["lat"], v1["lon"])
            ngo_names = ", ".join(
                get_ngo_info(v["mmsi"])["name"] for v in ngo_vessels
            )
            all_names = ", ".join(v.get("name") or v["mmsi"] for v in group[:4])

            severity = "critical" if hotspot else "high"
            self._emit(
                spike_type="rescue_cluster",
                mmsi=ngo_vessels[0]["mmsi"],
                name=ngo_vessels[0].get("name", ""),
                lat=v1["lat"],
                lon=v1["lon"],
                severity=severity,
                detail=(
                    f"Rescue cluster: {len(group)} vessels within "
                    f"{CLUSTER_RADIUS_NM:.0f}nm — NGO: {ngo_names} — "
                    f"vessels: {all_names}"
                    + (f" — zone: {hotspot}" if hotspot else "")
                ),
                ngo_info=get_ngo_info(ngo_vessels[0]["mmsi"]),
                metadata={"cluster_size": len(group), "vessel_names": all_names},
            )
            ngo_in_group.update(v["mmsi"] for v in ngo_vessels)

    # ── Emit helper ───────────────────────────────────────────────────────────

    def _emit(
        self,
        spike_type: str,
        mmsi: str,
        name: str,
        lat: float,
        lon: float,
        severity: str,
        detail: str,
        ngo_info: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        cooldown_key = f"{spike_type}:{mmsi}"
        now = time.monotonic()
        if self._emitted.get(cooldown_key, 0) + self._emit_cooldown_s > now:
            return
        self._emitted[cooldown_key] = now

        meta: dict[str, Any] = {"spike_type": spike_type}
        if ngo_info:
            meta["org"] = ngo_info.get("org", "")
            meta["vessel_role"] = ngo_info.get("role", "")
        if metadata:
            meta.update(metadata)

        # Cross-check against active distress cases: proximity + rescue-like
        # motion is context for "possible response", never proof of one --
        # same non-causal framing as add_nearby_humanitarian_context.
        if spike_type in _RESCUE_RELEVANT_SPIKES:
            nearby = _nearby_active_distress(lat, lon)
            if nearby is not None:
                meta["possible_response_to"] = nearby
                detail = (
                    f"{detail} — {nearby['distance_nm']} nm from an active distress "
                    f"report ({nearby['title'] or nearby['case_id']}); possible response, "
                    f"not confirmed."
                )
                if severity not in ("critical",):
                    severity = "critical"

        event = IntelEvent(
            type="ais_spike",
            severity=severity,
            lat=lat,
            lon=lon,
            title=f"AIS: {spike_type.replace('_', ' ').title()} — {name or mmsi}",
            text=detail,
            url=f"https://www.marinetraffic.com/en/ais/details/ships/{mmsi}",
            source="AIS Registry",
            linked_mmsi=mmsi,
            metadata=meta,
        )
        added = intel_store.add(event)
        if added:
            logger.info("AIS spike [%s] %s @ %.3f,%.3f", spike_type, name or mmsi, lat, lon)
            from core.intel.triangulation import evaluate as evaluate_triangulation
            evaluate_triangulation(event)
