# SPDX-License-Identifier: AGPL-3.0-or-later
"""Periodic dark-vessel / grey-zone scans over the AIS track store.

One background loop (default every MDA_SCAN_INTERVAL_S) runs the scans that need
a *history* rather than a single message:

  * rendezvous / ship-to-ship (STS)  -> `ais_rendezvous` IntelEvent
  * loitering near critical infrastructure (cable / pipeline / platform)
    -> `ais_anomaly` (anomaly_type = infra_proximity), domain grey_zone
  * deliberate AIS gap (jamming-aware)  -> `ais_anomaly` (anomaly_type = gap)

Per-message integrity checks (spoof patterns, identity screening) stay in
`core/anomaly/ais.py`. Everything emitted here flows through `intel_store` into
the existing fusion engine, which raises the correlated alert + case.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.config import config
from core.geo import haversine_km
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

_MED_BLACK_SEA = (-8.0, 28.0, 45.0, 48.0)  # min_lon, min_lat, max_lon, max_lat


def _nm(km: float) -> float:
    return km / 1.852


class MdaWatch:
    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # (mmsi_a, mmsi_b) -> {first_seen, last_seen, mid, count} for sustained-rendezvous
        self._pairs: dict[tuple[str, str], dict[str, Any]] = {}
        self._emitted: dict[str, float] = {}  # dedup key -> unix time

    def start(self) -> None:
        if self._running or not getattr(config, "MDA_WATCH_ENABLED", True):
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="mda-watch")
        self._thread.start()
        logger.info("MdaWatch started (interval=%ss)", getattr(config, "MDA_SCAN_INTERVAL_S", 300))

    def stop(self) -> None:
        self._running = False

    # ── loop ─────────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        time.sleep(60)  # let the track store fill after boot
        while self._running:
            try:
                self.scan()
            except Exception as exc:  # pragma: no cover
                logger.warning("MdaWatch scan error: %s", exc)
            time.sleep(int(getattr(config, "MDA_SCAN_INTERVAL_S", 300)))

    def scan(self) -> dict[str, int]:
        counts = {
            "rendezvous": self.scan_rendezvous(),
            "infra_loiter": self.scan_infra_loiter(),
            "gap": self.scan_gaps(),
            "identity": self.scan_identity(),
            "mmsi_duplicate": self.scan_mmsi_duplicate(),
        }
        # prune emit-dedup + stale pairs
        now = time.time()
        self._emitted = {k: t for k, t in self._emitted.items() if now - t < 24 * 3600}
        self._pairs = {k: v for k, v in self._pairs.items() if now - v["last_seen"] < 2 * 3600}
        return counts

    # ── rendezvous / STS ─────────────────────────────────────────────────────

    def scan_rendezvous(self) -> int:
        from core.mda.reference import reference
        from core.vessels.track_store import track_store

        window_min = float(getattr(config, "MDA_RENDEZVOUS_WINDOW_MIN", 30))
        max_sep_m = float(getattr(config, "MDA_RENDEZVOUS_MAX_SEP_M", 600))
        max_sog = float(getattr(config, "MDA_RENDEZVOUS_MAX_SOG_KN", 2.0))
        min_dur_min = float(getattr(config, "MDA_RENDEZVOUS_MIN_DURATION_MIN", 30))

        now = datetime.now(timezone.utc)
        rows = track_store.positions_between(now - timedelta(minutes=window_min), now,
                                             bbox=_MED_BLACK_SEA)
        # latest slow position per MMSI
        latest: dict[str, dict[str, Any]] = {}
        for r in rows:
            sog = r.get("sog") or 0.0
            if sog > max_sog + 1.0:
                continue
            prev = latest.get(r["mmsi"])
            if prev is None or r["ts"] > prev["ts"]:
                latest[r["mmsi"]] = r
        slow = [r for r in latest.values() if (r.get("sog") or 0.0) <= max_sog]
        slow.sort(key=lambda r: r["lon"])   # cheap sweep on longitude

        emitted = 0
        seen_now: set[tuple[str, str]] = set()
        for i, a in enumerate(slow):
            for b in slow[i + 1:]:
                if (b["lon"] - a["lon"]) * 96_000 > max_sep_m * 3:  # ~deg->m at 45N, early out
                    break
                sep_m = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) * 1000
                if sep_m > max_sep_m:
                    continue
                mid_lat, mid_lon = (a["lat"] + b["lat"]) / 2, (a["lon"] + b["lon"]) / 2
                if reference.in_port_or_anchorage(mid_lat, mid_lon):
                    continue
                _port, port_km = reference.nearest_port_km(mid_lat, mid_lon)
                if port_km < 5.0:
                    continue
                key = tuple(sorted((a["mmsi"], b["mmsi"])))
                seen_now.add(key)
                pair = self._pairs.setdefault(key, {"first_seen": time.time(), "count": 0})
                pair["last_seen"] = time.time()
                pair["count"] += 1
                pair["mid"] = (mid_lat, mid_lon)
                dur_min = (time.time() - pair["first_seen"]) / 60.0
                if dur_min >= min_dur_min and not self._recently_emitted(f"sts:{key[0]}:{key[1]}", 6 * 3600):
                    self._emit_rendezvous(key, mid_lat, mid_lon, dur_min)
                    emitted += 1
        return emitted

    def _emit_rendezvous(self, key: tuple[str, str], lat: float, lon: float, dur_min: float) -> None:
        from core.mda.reference import reference
        from core.vessels.registry import registry

        info = []
        tanker = False
        for mmsi in key:
            v = registry._cache.get(mmsi, {}) if hasattr(registry, "_cache") else {}
            st = v.get("ship_type")
            if isinstance(st, int) and 80 <= st <= 89:
                tanker = True
            info.append({"mmsi": mmsi, "name": v.get("ship_name") or mmsi,
                         "ship_type": st, "flag": v.get("flag")})
        zone = reference.in_sts_zone(lat, lon)
        dark = self._either_had_gap(key)
        severity = "high" if (tanker or zone or dark) else "medium"
        title = "STS rendezvous"
        if tanker:
            title = "Tanker STS rendezvous"
        if dark:
            title = "Dark " + title[0].lower() + title[1:]
        intel_store.add(IntelEvent(
            id=f"sts:{key[0]}:{key[1]}",
            type="ais_rendezvous",
            severity=severity,
            lat=round(lat, 5), lon=round(lon, 5),
            title=f"{title} — {info[0]['name']} / {info[1]['name']}",
            text=(f"MMSI {key[0]} and {key[1]} co-located within a few hundred metres, "
                  f"both near-stationary, for ~{int(dur_min)} min offshore"
                  + (f" in the {zone} STS zone" if zone else "") + "."),
            source="mda",
            linked_mmsi=key[0],
            metadata={
                "anomaly_type": "ais_rendezvous",
                "maritime_domain": "sanctions",
                "is_distress": False,
                "publication_status": "internal",
                "source_policy": "official_api",
                "verification_status": "ais_transponder",
                "coordinate_source": "ais_position",
                "vessels": info, "duration_min": round(dur_min, 1),
                "sts_zone": zone, "tanker": tanker, "dark": dark,
            },
        ), dedup_key=f"sts:{key[0]}:{key[1]}:{int(time.time() // 21600)}")
        logger.warning("MDA: STS rendezvous %s <-> %s (%dmin, tanker=%s dark=%s zone=%s)",
                       key[0], key[1], int(dur_min), tanker, dark, zone)

    def _either_had_gap(self, key: tuple[str, str]) -> bool:
        for ev in intel_store.events(limit=400):
            if (ev.type == "ais_anomaly" and ev.linked_mmsi in key
                    and (ev.metadata.get("anomaly_type") in {"gap", "long_gap"})):
                return True
        return False

    # ── infrastructure loitering ─────────────────────────────────────────────

    def scan_infra_loiter(self) -> int:
        from core.mda.reference import reference
        from core.vessels.track_store import track_store

        buf_km = float(getattr(config, "MDA_INFRA_BUFFER_KM", 3.0))
        max_sog = float(getattr(config, "MDA_INFRA_LOITER_MAX_SOG_KN", 3.0))
        min_dur_min = float(getattr(config, "MDA_INFRA_LOITER_MIN_MIN", 45))

        now = datetime.now(timezone.utc)
        rows = track_store.positions_between(now - timedelta(minutes=min_dur_min * 1.5), now,
                                             bbox=_MED_BLACK_SEA)
        by_mmsi: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            by_mmsi.setdefault(r["mmsi"], []).append(r)

        emitted = 0
        for mmsi, track in by_mmsi.items():
            track.sort(key=lambda r: r["ts"])
            slow = [r for r in track if (r.get("sog") or 0.0) <= max_sog]
            if len(slow) < 3:
                continue
            span_min = (_parse(slow[-1]["ts"]) - _parse(slow[0]["ts"])).total_seconds() / 60.0
            if span_min < min_dur_min:
                continue
            mid = slow[len(slow) // 2]
            hit = reference.nearest_infrastructure(mid["lat"], mid["lon"], max_km=buf_km)
            if hit is None or hit.kind not in ("cable", "pipeline", "platform"):
                continue
            if self._recently_emitted(f"infra:{mmsi}:{hit.name}", 12 * 3600):
                continue
            from core.vessels.registry import registry
            v = registry._cache.get(mmsi, {}) if hasattr(registry, "_cache") else {}
            intel_store.add(IntelEvent(
                id=f"infraloiter:{mmsi}",
                type="ais_anomaly",
                severity="high" if hit.kind in ("cable", "pipeline") else "medium",
                lat=round(mid["lat"], 5), lon=round(mid["lon"], 5),
                title=f"Loitering near {hit.name} — {v.get('ship_name') or mmsi}",
                text=(f"MMSI {mmsi} at <{max_sog:.0f} kn for ~{int(span_min)} min within "
                      f"{hit.distance_km:.1f} km of {hit.name} ({hit.kind})."),
                source="mda", linked_mmsi=mmsi,
                metadata={
                    "anomaly_type": "cable_proximity" if hit.kind == "cable" else "loiter",
                    "maritime_domain": "grey_zone", "is_distress": False,
                    "publication_status": "internal", "source_policy": "official_api",
                    "verification_status": "ais_transponder", "coordinate_source": "ais_position",
                    "infrastructure": {"kind": hit.kind, "name": hit.name, "distance_km": hit.distance_km},
                    "loiter_minutes": round(span_min, 1),
                },
            ), dedup_key=f"infraloiter:{mmsi}:{int(time.time() // 43200)}")
            logger.warning("MDA: %s loitering near %s (%s, %.1fkm, %dmin)",
                           mmsi, hit.name, hit.kind, hit.distance_km, int(span_min))
            emitted += 1
        return emitted

    # ── deliberate AIS gap (jamming-aware) ───────────────────────────────────

    def scan_gaps(self) -> int:
        from core.mda.jamming import jamming
        from core.vessels.track_store import track_store

        min_gap = float(getattr(config, "MDA_GAP_MIN_S", 3600))
        candidates = track_store.silent_since(min_silent_s=min_gap, min_speed_kn=2.0)
        emitted = 0
        for mmsi, last in candidates:
            if self._recently_emitted(f"gap:{mmsi}", 6 * 3600):
                continue
            jam = jamming.in_jamming_zone(last.lat, last.lon)
            confidence = round(max(0.2, min(0.9, 0.4 + (time.time() - last.ts) / 14400) - 0.5 * jam), 3)
            severity = "high" if confidence >= 0.7 else "medium"
            intel_store.add(IntelEvent(
                id=f"aisgap:{mmsi}",
                type="ais_anomaly",
                severity=severity,
                lat=round(last.lat, 5), lon=round(last.lon, 5),
                title=f"AIS gap — {last.name or mmsi}",
                text=(f"MMSI {mmsi} last heard underway ({last.sog:.0f} kn) "
                      f"{int((time.time() - last.ts) / 60)} min ago, then silent."
                      + (" Inside an active GNSS-jamming zone (likely reception loss)." if jam > 0.3 else "")),
                source="mda", linked_mmsi=mmsi,
                metadata={
                    "anomaly_type": "long_gap" if (time.time() - last.ts) > 6 * 3600 else "gap",
                    "maritime_domain": "sanctions" if jam < 0.3 else "grey_zone",
                    "is_distress": False, "publication_status": "internal",
                    "source_policy": "official_api", "verification_status": "ais_transponder",
                    "coordinate_source": "ais_position",
                    "silent_seconds": int(time.time() - last.ts),
                    "jamming_score": jam, "anomaly_confidence": confidence,
                },
            ), dedup_key=f"aisgap:{mmsi}:{int(time.time() // 21600)}")
            emitted += 1
        return emitted

    # ── identity screening ──────────────────────────────────────────────────

    def scan_identity(self) -> int:
        from core.mda.identity import screen
        from core.vessels.registry import registry
        from core.vessels.track_store import track_store

        cache = getattr(registry, "_cache", {}) or {}
        now = datetime.now(timezone.utc)
        recent = {r["mmsi"] for r in track_store.positions_between(
            now - timedelta(hours=6), now, bbox=_MED_BLACK_SEA, limit=100_000)}
        emitted = 0
        for mmsi in list(recent)[:2000]:
            v = cache.get(mmsi, {})
            result = screen(mmsi=mmsi, imo=v.get("imo"), name=v.get("ship_name") or "",
                            flag=v.get("flag") or "")
            serious = {"sanctions_hit"} & set(result["risk_flags"])
            weak = {f for f in result["risk_flags"] if f.startswith("mmsi_")} | \
                   ({"imo_checksum_fail"} & set(result["risk_flags"]))
            if not serious and len(weak) < 1:
                continue
            if self._recently_emitted(f"ident:{mmsi}", 24 * 3600):
                continue
            last = track_store._last.get(mmsi)
            lat = last.lat if last else None
            lon = last.lon if last else None
            intel_store.add(IntelEvent(
                id=f"vesselid:{mmsi}",
                type="vessel_identity",
                severity="high" if serious else "medium",
                lat=lat, lon=lon,
                title=(f"Sanctioned vessel: {v.get('ship_name') or mmsi}" if serious
                       else f"Identity anomaly: {v.get('ship_name') or mmsi}"),
                text=(f"MMSI {mmsi} — flags: {', '.join(result['risk_flags'])}."
                      + (f" Sanctions: {result['sanctions'][0]['list']} "
                         f"({result['sanctions'][0].get('program', '')})." if serious else "")),
                source="mda", linked_mmsi=mmsi,
                metadata={
                    "anomaly_type": "sdn_match" if serious else "identity_anomaly",
                    "maritime_domain": "sanctions", "is_distress": False,
                    "publication_status": "internal", "source_policy": "official_api",
                    "verification_status": "derived", "coordinate_source": "ais_position",
                    "identity": result,
                },
            ), dedup_key=f"vesselid:{mmsi}:{int(time.time() // 86400)}")
            emitted += 1
        return emitted

    def scan_mmsi_duplicate(self) -> int:
        """Same MMSI transmitting from two places far apart in the same window —
        the classic clone / borrowed-identity signature."""
        from core.vessels.track_store import track_store

        now = datetime.now(timezone.utc)
        rows = track_store.positions_between(now - timedelta(minutes=40), now, bbox=_MED_BLACK_SEA)
        by_mmsi: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            by_mmsi.setdefault(r["mmsi"], []).append(r)
        emitted = 0
        for mmsi, pts in by_mmsi.items():
            if len(pts) < 4:
                continue
            far = 0
            base = pts[0]
            for p in pts[1:]:
                if haversine_km(base["lat"], base["lon"], p["lat"], p["lon"]) > 100:
                    far += 1
            if far < 2:
                continue
            if self._recently_emitted(f"dup:{mmsi}", 12 * 3600):
                continue
            intel_store.add(IntelEvent(
                id=f"mmsidup:{mmsi}",
                type="vessel_identity",
                severity="high",
                lat=round(base["lat"], 5), lon=round(base["lon"], 5),
                title=f"Duplicate MMSI {mmsi} — two positions >100 km apart",
                text=(f"MMSI {mmsi} broadcast from two widely separated positions within "
                      f"40 min — clone / borrowed identity or a spoofed track."),
                source="mda", linked_mmsi=mmsi,
                metadata={
                    "anomaly_type": "mmsi_duplicate", "maritime_domain": "sanctions",
                    "is_distress": False, "publication_status": "internal",
                    "source_policy": "official_api", "verification_status": "derived",
                    "coordinate_source": "ais_position",
                },
            ), dedup_key=f"mmsidup:{mmsi}:{int(time.time() // 43200)}")
            emitted += 1
        return emitted

    # ── helpers ──────────────────────────────────────────────────────────────

    def _recently_emitted(self, key: str, cooldown_s: float) -> bool:
        now = time.time()
        if now - self._emitted.get(key, 0.0) < cooldown_s:
            return True
        self._emitted[key] = now
        return False


def _parse(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


mda_watch = MdaWatch()
