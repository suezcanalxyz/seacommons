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
            "spoofing": self.scan_spoofing(),
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

        from core.vessels.registry import registry
        cache = getattr(registry, "_cache", {}) or {}
        emitted = 0
        for mmsi, track in by_mmsi.items():
            track.sort(key=lambda r: r["ts"])
            slow = [r for r in track if (r.get("sog") or 0.0) <= max_sog]
            if len(slow) < 4:
                continue
            span_min = (_parse(slow[-1]["ts"]) - _parse(slow[0]["ts"])).total_seconds() / 60.0
            if span_min < min_dur_min:
                continue
            # must actually dwell, not just transit slowly through the buffer
            lats = [r["lat"] for r in slow]
            lons = [r["lon"] for r in slow]
            dwell_km = haversine_km(min(lats), min(lons), max(lats), max(lons))
            if dwell_km > 5.0:
                continue
            v = cache.get(mmsi, {})
            st = v.get("ship_type")
            if isinstance(st, int) and 30 <= st <= 32:   # fishing vessels work slowly everywhere
                continue
            if st == 52:   # tugs work slowly near port infrastructure by design
                continue
            mid = slow[len(slow) // 2]
            hit = reference.nearest_infrastructure(mid["lat"], mid["lon"], max_km=buf_km)
            if hit is None or hit.kind not in ("cable", "pipeline", "sts_zone"):
                continue
            # A vessel idling in a bunkering / STS anchorage is not itself
            # unusual -- that is what the zone is for. It becomes worth
            # surfacing when the vessel loitering there is a confirmed
            # sanctions match: a classic evasion pattern (refuel/transfer at
            # a grey-zone hub instead of a port call), cross-referenced here
            # even without a second vessel for scan_rendezvous to pair it
            # with. cable/pipeline proximity stays unconditional -- that is
            # infrastructure-safety context regardless of who the vessel is.
            sanctioned = False
            if hit.kind == "sts_zone":
                from core.mda.identity import screen
                result = screen(mmsi=mmsi, imo=v.get("imo"),
                                name=v.get("ship_name") or "", flag=v.get("flag") or "")
                sanctioned = bool(result.get("sanctions"))
                if not sanctioned:
                    continue
            if self._recently_emitted(f"infra:{mmsi}:{hit.name}", 24 * 3600):
                continue
            intel_store.add(IntelEvent(
                id=f"infraloiter:{mmsi}",
                type="ais_anomaly",
                severity="high",
                lat=round(mid["lat"], 5), lon=round(mid["lon"], 5),
                title=(f"Sanctioned vessel loitering in {hit.name} — {v.get('ship_name') or mmsi}"
                       if sanctioned else f"Loitering near {hit.name} — {v.get('ship_name') or mmsi}"),
                text=(f"MMSI {mmsi} at <{max_sog:.0f} kn for ~{int(span_min)} min within "
                      f"{hit.distance_km:.1f} km of {hit.name} ({hit.kind})."
                      + (" Vessel is a confirmed sanctions match." if sanctioned else "")),
                url=f"https://www.marinetraffic.com/en/ais/details/ships/mmsi:{mmsi}",
                source="SeaCommons AIS analysis", linked_mmsi=mmsi,
                metadata={
                    "anomaly_type": (
                        "sanctions_bunkering_loiter" if sanctioned
                        else "cable_proximity" if hit.kind == "cable" else "loiter"
                    ),
                    "maritime_domain": "sanctions" if sanctioned else "grey_zone",
                    "is_distress": False,
                    "publication_status": "internal", "source_policy": "official_api",
                    "verification_status": "ais_transponder", "coordinate_source": "ais_position",
                    "infrastructure": {"kind": hit.kind, "name": hit.name, "distance_km": hit.distance_km},
                    "loiter_minutes": round(span_min, 1),
                    "sanctions_matched": sanctioned,
                    "detection_reason": (
                        f"AIS dwell: {len(slow)} slow fixes over {int(span_min)} minutes, "
                        f"within {hit.distance_km:.1f} km of {hit.name}; proximity is "
                        "anomaly context, not evidence of interference."
                    ),
                },
            ), dedup_key=f"infraloiter:{mmsi}:{int(time.time() // 43200)}")
            logger.warning("MDA: %s loitering near %s (%s, %.1fkm, %dmin)",
                           mmsi, hit.name, hit.kind, hit.distance_km, int(span_min))
            emitted += 1
        return emitted

    # ── deliberate AIS gap (jamming-aware) ───────────────────────────────────

    def scan_gaps(self) -> int:
        from core.intel import confidence as confidence_mod
        from core.mda.jamming import jamming
        from core.vessels.registry import registry
        from core.vessels.track_store import track_store

        min_gap = float(getattr(config, "MDA_GAP_MIN_S", 3600))
        candidates = track_store.silent_since(min_silent_s=min_gap, min_speed_kn=2.0)
        cache = getattr(registry, "_cache", {}) or {}
        emitted = 0
        for mmsi, last in candidates:
            if self._recently_emitted(f"gap:{mmsi}", 6 * 3600):
                continue
            # AIS ship_type 36/37 = sailing / pleasure craft. These routinely
            # switch off AIS overnight at anchor near a marina -- that is
            # normal leisure behaviour, not a reporting anomaly, and must not
            # be reported as one unless the vessel itself is a sanctions
            # match (see core.mda.identity.screen).
            v = cache.get(mmsi, {})
            ship_type = v.get("ship_type")
            if isinstance(ship_type, int) and ship_type in (36, 37):
                from core.mda.identity import screen
                result = screen(
                    mmsi=mmsi, imo=v.get("imo"),
                    name=v.get("ship_name") or "", flag=v.get("flag") or "",
                )
                if not result.get("sanctions"):
                    continue
            # AIS ship_type 60-69 = passenger vessel (ferries included).
            # Scheduled commercial traffic is a different data vertical from
            # maritime-security anomalies -- kept out of Live for now (not
            # deleted: the detection itself is unchanged and still runs,
            # this only withholds passenger-vessel results from this feed)
            # until it has its own destination separate from this one.
            if isinstance(ship_type, int) and 60 <= ship_type <= 69:
                from core.mda.identity import screen
                result = screen(
                    mmsi=mmsi, imo=v.get("imo"),
                    name=v.get("ship_name") or "", flag=v.get("flag") or "",
                )
                if not result.get("sanctions"):
                    continue
            # AIS ship_type 30-32 = fishing vessel. Fishing boats routinely
            # work slowly or go dark far from any port while actually
            # fishing -- scan_infra_loiter already exempts this ship_type
            # blanket ("fishing vessels work slowly everywhere"); a gap is
            # the same normal-work pattern, not an anomaly.
            if isinstance(ship_type, int) and 30 <= ship_type <= 32:
                from core.mda.identity import screen
                result = screen(
                    mmsi=mmsi, imo=v.get("imo"),
                    name=v.get("ship_name") or "", flag=v.get("flag") or "",
                )
                if not result.get("sanctions"):
                    continue
            # AIS ship_type 52 = tug. Port tugs sit idle waiting for the next
            # job and go dark between assignments -- observed live: Genoa
            # tug traffic showing the same false-gap pattern as fishing
            # vessels do. Same exemption.
            if ship_type == 52:
                from core.mda.identity import screen
                result = screen(
                    mmsi=mmsi, imo=v.get("imo"),
                    name=v.get("ship_name") or "", flag=v.get("flag") or "",
                )
                if not result.get("sanctions"):
                    continue
            jam = jamming.in_jamming_zone(last.lat, last.lon)
            cue = None
            if jam < 0.3:   # not just jamming — worth a satellite cross-cue
                try:
                    from core.mda.darkship_cue import build as _cue
                    course = _last_course(track_store, mmsi)
                    cue = _cue(lat=last.lat, lon=last.lon, course_deg=course,
                               speed_kn=last.sog,
                               gap_start=datetime.fromtimestamp(last.ts, tz=timezone.utc))
                except Exception as exc:  # pragma: no cover
                    logger.debug("darkship_cue failed: %s", exc)
            confidence = round(max(0.2, min(0.9, 0.4 + (time.time() - last.ts) / 14400) - 0.5 * jam), 3)
            severity = "high" if confidence >= 0.7 else "medium"
            # Shadow-mode confidence model (docs/prompt.md phase 9/11): a
            # second, traceable score computed alongside the inline formula
            # above. Stored, not cut over -- severity/publication behaviour
            # here is still driven entirely by `confidence`/`severity` above,
            # unchanged. Lets the two be compared before anything switches.
            silent_s = time.time() - last.ts
            gap_rule = "ais_gap_long" if silent_s > 6 * 3600 else "ais_gap"
            confidence_v2 = confidence_mod.combine(
                gap_rule,
                rule_strength=confidence_mod.rule_strength(gap_rule),
                source_reliability=confidence_mod.source_reliability("official_api"),
                observation_freshness=confidence_mod.observation_freshness(silent_s),
                coverage_quality=confidence_mod.coverage_quality(jam),
                location_precision=confidence_mod.location_precision_score("ais_position"),
            )
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
                    # A reporting gap is a traffic anomaly.  It becomes
                    # sanctions context only when identity screening finds a
                    # real list match on this vessel.
                    "maritime_domain": "grey_zone",
                    "is_distress": False, "publication_status": "internal",
                    "source_policy": "official_api", "verification_status": "ais_transponder",
                    "coordinate_source": "ais_position",
                    "silent_seconds": int(time.time() - last.ts),
                    "jamming_score": jam, "anomaly_confidence": confidence,
                    "confidence_v2": confidence_v2.as_metadata(),
                    "darkship_cue": cue,
                },
            ), dedup_key=f"aisgap:{mmsi}:{int(time.time() // 21600)}")
            emitted += 1
        return emitted

    # ── identity screening ──────────────────────────────────────────────────

    @staticmethod
    def _identity_fingerprint(result: dict[str, Any]) -> list:
        sanctions = sorted(
            (s.get("list", ""), s.get("program", "")) for s in (result.get("sanctions") or [])
        )
        return [sorted(result.get("risk_flags") or []), sanctions]

    def _identity_status_changed(self, mmsi: str, result: dict[str, Any]) -> bool:
        """True on first sighting of this MMSI's flagged status, or if it
        changed since the last emitted vessel_identity event for it (new
        sanctions program, escalation from a weak flag to sanctions_hit,
        etc). id=f"vesselid:{mmsi}" is deterministic -- one row per vessel,
        looked up directly rather than re-scanning the event stream."""
        fingerprint = self._identity_fingerprint(result)
        try:
            from core.db.models import IntelEventDB
            from core.db.session import session_scope

            with session_scope() as db:
                row = db.query(IntelEventDB).filter(
                    IntelEventDB.id == f"vesselid:{mmsi}"
                ).first()
                if row is None:
                    return True
                previous = (row.meta or {}).get("identity_fingerprint")
                return previous != fingerprint
        except Exception as exc:  # pragma: no cover - fail open, same as before this change
            logger.debug("identity fingerprint lookup failed for %s: %s", mmsi, exc)
            return True

    def scan_identity(self) -> int:
        from core.mda.identity import screen
        from core.vessels.registry import registry
        from core.vessels.track_store import track_store

        cache = getattr(registry, "_cache", {}) or {}
        now = datetime.now(timezone.utc)
        rows = track_store.positions_between(
            now - timedelta(hours=6), now, bbox=_MED_BLACK_SEA, limit=100_000)
        # track_store._last is an in-memory, per-process cache of live AIS
        # messages — empty right after a restart even though these rows (from
        # the DB) prove the vessel has a recent position. Take the latest fix
        # per MMSI from the rows we already fetched instead of a second,
        # unreliable lookup — every match previously shipped with
        # lat/lon = None and simply couldn't be plotted.
        last_pos: dict[str, tuple[float, float]] = {}
        for r in rows:  # ordered ts ascending -- later rows overwrite, so this ends up latest-wins
            last_pos[r["mmsi"]] = (r["lat"], r["lon"])
        emitted = 0
        for mmsi in list(last_pos)[:2000]:
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
            # Sanctions/identity status is a persistent property of the
            # vessel, not a recurring event -- re-alerting every 24h for as
            # long as a known-sanctioned vessel keeps transiting the Med is
            # exactly the "map noise" docs/prompt.md warns about. Only emit
            # when this is either the first sighting or the flagged status
            # actually changed (new list, new program, escalation from a
            # weak flag to a real sanctions hit).
            if not self._identity_status_changed(mmsi, result):
                continue
            lat, lon = last_pos[mmsi]
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
                    "identity_fingerprint": self._identity_fingerprint(result),
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

    # ── spoofing patterns ───────────────────────────────────────────────────

    def scan_spoofing(self) -> int:
        from core.intel import confidence as confidence_mod
        from core.mda.jamming import jamming
        from core.vessels.registry import registry
        from core.vessels.track_store import track_store

        now = datetime.now(timezone.utc)
        rows = track_store.positions_between(now - timedelta(minutes=90), now, bbox=_MED_BLACK_SEA)
        by_mmsi: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            by_mmsi.setdefault(r["mmsi"], []).append(r)
        cache = getattr(registry, "_cache", {}) or {}
        emitted = 0
        for mmsi, pts in by_mmsi.items():
            if len(pts) < 6:
                continue
            pts.sort(key=lambda r: r["ts"])
            reason, extra = self._spoof_signature(pts)
            if reason is None:
                continue
            if reason in ("frozen", "circular"):
                # A pleasure/sailing craft (ship_type 36/37) swinging on its
                # anchor near a marina produces exactly this signature --
                # near-static or a small drift circle. Real, not spoofed.
                # Same exemption as scan_gaps: only a confirmed sanctions
                # match overrides it.
                v = cache.get(mmsi, {})
                ship_type = v.get("ship_type")
                if isinstance(ship_type, int) and ship_type in (36, 37):
                    from core.mda.identity import screen
                    result = screen(
                        mmsi=mmsi, imo=v.get("imo"),
                        name=v.get("ship_name") or "", flag=v.get("flag") or "",
                    )
                    if not result.get("sanctions"):
                        continue
                # AIS ship_type 60-69 = passenger vessel -- kept out of Live
                # for now, same reasoning and same sanctions override as
                # scan_gaps above (detection unchanged, just not surfaced
                # here until it has its own destination).
                elif isinstance(ship_type, int) and 60 <= ship_type <= 69:
                    from core.mda.identity import screen
                    result = screen(
                        mmsi=mmsi, imo=v.get("imo"),
                        name=v.get("ship_name") or "", flag=v.get("flag") or "",
                    )
                    if not result.get("sanctions"):
                        continue
                # AIS ship_type 30-32 = fishing vessel. A trawler working a
                # ground draws exactly the "circular" signature -- repeated
                # tight loops/passes are how trawling works, not spoofing.
                elif isinstance(ship_type, int) and 30 <= ship_type <= 32:
                    from core.mda.identity import screen
                    result = screen(
                        mmsi=mmsi, imo=v.get("imo"),
                        name=v.get("ship_name") or "", flag=v.get("flag") or "",
                    )
                    if not result.get("sanctions"):
                        continue
                # AIS ship_type 52 = tug. Repeated short manoeuvres assisting
                # ships in/out of port, then idling near the breakwater
                # between jobs, draws the same near-static/tight-ring
                # signature -- observed live in Genoa traffic.
                elif ship_type == 52:
                    from core.mda.identity import screen
                    result = screen(
                        mmsi=mmsi, imo=v.get("imo"),
                        name=v.get("ship_name") or "", flag=v.get("flag") or "",
                    )
                    if not result.get("sanctions"):
                        continue
            if self._recently_emitted(f"spoof:{mmsi}", 6 * 3600):
                continue
            mid = pts[len(pts) // 2]
            jam = jamming.in_jamming_zone(mid["lat"], mid["lon"])
            atype = "position_jump" if reason == "teleport" else (
                "circle_spoof" if reason == "circular" else "static_spoof")
            # Shadow-mode confidence model (docs/prompt.md phase 9/11) --
            # this detector had no confidence value at all before, only
            # severity from jamming alone. Stored alongside severity, not
            # driving it yet.
            spoof_rule = {"teleport": "spoof_teleport", "circular": "spoof_circular",
                          "frozen": "spoof_frozen"}.get(reason, "spoof_frozen")
            duration_s = max(0.0, (_parse(pts[-1]["ts"]) - _parse(pts[0]["ts"])).total_seconds())
            confidence_v2 = confidence_mod.combine(
                spoof_rule,
                rule_strength=confidence_mod.rule_strength(spoof_rule),
                source_reliability=confidence_mod.source_reliability("derived"),
                persistence=confidence_mod.persistence(len(pts), duration_s),
                coverage_quality=confidence_mod.coverage_quality(jam),
                location_precision=confidence_mod.location_precision_score("ais_position"),
            )
            intel_store.add(IntelEvent(
                id=f"spoof:{mmsi}:{reason}",
                type="ais_anomaly",
                severity="high" if jam < 0.4 else "medium",
                lat=round(mid["lat"], 5), lon=round(mid["lon"], 5),
                title=f"AIS {reason} spoofing — {mmsi}",
                text=f"MMSI {mmsi}: {reason} track signature ({extra})."
                     + (" Active GNSS jamming in the area." if jam > 0.3 else ""),
                source="mda", linked_mmsi=mmsi,
                metadata={
                    "anomaly_type": atype, "maritime_domain": "grey_zone",
                    "is_distress": False, "publication_status": "internal",
                    "source_policy": "official_api", "verification_status": "derived",
                    "coordinate_source": "ais_position", "spoof_reason": reason,
                    "jamming_score": jam, "detail": extra,
                    "confidence_v2": confidence_v2.as_metadata(),
                },
            ), dedup_key=f"spoof:{mmsi}:{reason}:{int(time.time() // 21600)}")
            emitted += 1
        return emitted

    @staticmethod
    def _spoof_signature(pts: list[dict[str, Any]]) -> tuple[Optional[str], str]:
        # teleport: a single step implies an impossible speed
        for a, b in zip(pts, pts[1:]):
            dt = (_parse(b["ts"]) - _parse(a["ts"])).total_seconds()
            if dt <= 0:
                continue
            kn = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) / 1.852 / (dt / 3600)
            if kn > 60 and haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) > 15:
                return "teleport", f"{kn:.0f} kn between two fixes"
        # frozen: >80% of fixes identical position while SOG > 1
        first = (round(pts[0]["lat"], 4), round(pts[0]["lon"], 4))
        same = sum(1 for p in pts if (round(p["lat"], 4), round(p["lon"], 4)) == first)
        moving = sum(1 for p in pts if (p.get("sog") or 0) > 1.0)
        if same / len(pts) > 0.8 and moving > len(pts) * 0.5:
            return "frozen", f"{same}/{len(pts)} fixes identical while SOG>1"
        # circular: least-squares circle fit, small residual, plausible radius
        r_m, resid_ratio = _circle_fit([(p["lat"], p["lon"]) for p in pts])
        if r_m and 40 <= r_m <= 3000 and resid_ratio < 0.12:
            return "circular", f"ring radius ~{r_m:.0f} m"
        return None, ""

    # ── helpers ──────────────────────────────────────────────────────────────

    def _recently_emitted(self, key: str, cooldown_s: float) -> bool:
        now = time.time()
        if now - self._emitted.get(key, 0.0) < cooldown_s:
            return True
        self._emitted[key] = now
        return False


def _last_course(track_store: Any, mmsi: str) -> Optional[float]:
    from datetime import datetime as _dt
    pts = track_store.track(mmsi, since=_dt.now(timezone.utc) - timedelta(hours=3), limit=20)
    for p in reversed(pts):
        if p.get("cog") is not None:
            return float(p["cog"])
    if len(pts) >= 2:
        a, b = pts[-2], pts[-1]
        from core.geo import bearing_deg
        return bearing_deg(a["lat"], a["lon"], b["lat"], b["lon"])
    return None


def _circle_fit(latlon: list[tuple[float, float]]) -> tuple[Optional[float], float]:
    """Kasa least-squares circle fit in a local metre frame. Returns
    (radius_m, mean_residual / radius); radius None when degenerate.

    Model: x^2 + y^2 = a*x + b*y + c  ->  centre (a/2, b/2), r = sqrt(c + a^2/4 + b^2/4).
    """
    if len(latlon) < 5:
        return None, 1.0
    try:
        import numpy as np
    except Exception:  # pragma: no cover
        return None, 1.0
    lat0 = sum(p[0] for p in latlon) / len(latlon)
    lon0 = sum(p[1] for p in latlon) / len(latlon)
    mlat = 111_320.0
    mlon = 111_320.0 * math.cos(math.radians(lat0))
    x = np.array([(p[1] - lon0) * mlon for p in latlon])
    y = np.array([(p[0] - lat0) * mlat for p in latlon])
    A = np.column_stack([x, y, np.ones_like(x)])
    z = x * x + y * y
    try:
        a, b, c = np.linalg.lstsq(A, z, rcond=None)[0]
    except Exception:  # pragma: no cover
        return None, 1.0
    cx, cy = a / 2.0, b / 2.0
    inside = c + cx * cx + cy * cy
    if inside <= 0:
        return None, 1.0
    r = math.sqrt(inside)
    resid = float(np.mean(np.abs(np.hypot(x - cx, y - cy) - r)))
    return r, resid / r if r > 0 else 1.0


def _parse(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


mda_watch = MdaWatch()
