# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vessel incidents from the live AIS feed.

Open-source and live: every ship broadcasts its own navigational status and
distress beacons over AIS, which SeaCommons already ingests via AISStream.
This monitor turns the operationally meaningful ones into canonical intel
events:

  * AIS-SART / AIS-MOB / AIS-EPIRB (MMSI 970/972/974*, or nav status 14) --
    an active distress beacon. Emitted immediately, as a distress.
  * Aground (nav status 6) -- a grounding. Emitted once the status is
    sustained, as a vessel incident.
  * Not under command (nav status 2) -- a vessel unable to manoeuvre.
    Emitted once sustained, but left for operator review rather than
    auto-published (it is frequently set for benign reasons).

Restricted-manoeuvrability (nav 3) is deliberately ignored -- dredgers,
cable layers and survey vessels broadcast it continuously.

The monitor is driven by aisstream.register_position_hook, so it shares the
single AISStream connection (the free tier allows only one socket per key).
State is in memory; a restart re-learns from the next few minutes of feed.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

# nav status -> (kind, severity, is_distress, auto_publish, min_reports, min_span_s)
# A grounded vessel is an operational incident (breakup / pollution / crew at
# risk); "not under command" is left for operator review.
_INCIDENT_STATUS: dict[int, tuple[str, str, bool, bool, int, float]] = {
    6: ("aground", "high", True, True, 2, 180.0),
    2: ("not_under_command", "medium", False, False, 3, 600.0),
}
# Plain-language label for the raw `kind` — this is what operators (and the
# public feed) actually read; the technical AIS nav-status name stays in
# metadata (ais_nav_status_kind) for anyone who wants it.
_KIND_LABEL = {
    "aground": "Vessel ran aground",
    "not_under_command": "Vessel unable to manoeuvre",
    "distress_beacon": "Distress beacon activated",
}
_BEACON_STATUS = 14
_BEACON_MMSI_PREFIXES = ("970", "972", "974")
_BEACON_SOURCE = {"970": "ais_sart", "972": "ais_mob", "974": "ais_epirb"}
_NORMAL_STATUS = frozenset({0, 1, 5, 8})
_EMIT_COOLDOWN_S = 6 * 3600
_EPISODE_UPDATE_INTERVAL_S = 5 * 60
_STATE_TTL_S = 12 * 3600


class VesselIncidentMonitor:
    def __init__(self) -> None:
        self._running = False
        # mmsi -> {status, first_seen, count, last_lat, last_lon, name}
        self._episodes: dict[str, dict] = {}
        # (mmsi, kind) -> unix time of last emit
        self._emitted: dict[tuple[str, str], float] = {}
        self._updated: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()
        self._last_prune = 0.0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        from core.vessels import aisstream

        aisstream.register_position_hook(self.on_position)
        logger.info("VesselIncidentMonitor attached to the AIS feed")

    def stop(self) -> None:
        self._running = False

    def on_position(
        self,
        mmsi: str,
        name: str,
        lat: float,
        lon: float,
        sog: float | None,
        nav_status: int | None = None,
        *_extra,
    ) -> None:
        if not self._running or not mmsi:
            return
        now = time.time()
        if now - self._last_prune > 1800:
            self._prune(now)

        beacon_source = self._beacon_source(mmsi, nav_status)
        if beacon_source is not None:
            self._emit(
                mmsi, name, lat, lon,
                kind="distress_beacon", source=beacon_source,
                severity="critical", is_distress=True, auto_publish=True,
            )
            return

        if nav_status is None:
            return
        with self._lock:
            if nav_status in _NORMAL_STATUS:
                previous = self._episodes.pop(mmsi, None)
                if previous is not None:
                    rule = _INCIDENT_STATUS.get(previous["status"])
                    if rule is not None:
                        kind = rule[0]
                        intel_store.update_vessel_episode(
                            f"aisinc:{mmsi}:{kind}",
                            lat=lat,
                            lon=lon,
                            timestamp_utc=datetime.now(timezone.utc).isoformat(),
                            sog=sog,
                            nav_status=nav_status,
                            incident_lifecycle="resolved",
                        )
                return
            rule = _INCIDENT_STATUS.get(nav_status)
            if rule is None:
                return
            kind, severity, is_distress, auto_publish, min_reports, min_span_s = rule
            episode = self._episodes.get(mmsi)
            if episode is None or episode["status"] != nav_status:
                self._episodes[mmsi] = {
                    "status": nav_status, "first_seen": now, "count": 1,
                    "lat": lat, "lon": lon, "name": name,
                }
                return
            episode["count"] += 1
            episode["lat"], episode["lon"] = lat, lon
            if episode["name"] == "" and name:
                episode["name"] = name
            sustained = (
                episode["count"] >= min_reports
                and now - episode["first_seen"] >= min_span_s
            )
            if not sustained:
                return

        self._emit(
            mmsi, name or "", lat, lon,
            kind=kind, source="ais", severity=severity,
            is_distress=is_distress, auto_publish=auto_publish,
            sog=sog, nav_status=nav_status,
            reports=episode["count"], sustained_s=round(now - episode["first_seen"]),
            min_reports=min_reports, min_span_s=min_span_s,
        )

    @staticmethod
    def _beacon_source(mmsi: str, nav_status: int | None) -> str | None:
        for prefix, source in _BEACON_SOURCE.items():
            if mmsi.startswith(prefix):
                return source
        if nav_status == _BEACON_STATUS:
            return "ais_sart"
        return None

    def _emit(
        self,
        mmsi: str,
        name: str,
        lat: float,
        lon: float,
        *,
        kind: str,
        source: str,
        severity: str,
        is_distress: bool,
        auto_publish: bool,
        sog: float | None = None,
        nav_status: int | None = None,
        reports: int | None = None,
        sustained_s: int | None = None,
        min_reports: int | None = None,
        min_span_s: float | None = None,
    ) -> None:
        now = time.time()
        key = (mmsi, kind)
        with self._lock:
            if now - self._emitted.get(key, 0.0) < _EMIT_COOLDOWN_S:
                if now - self._updated.get(key, 0.0) >= _EPISODE_UPDATE_INTERVAL_S:
                    self._updated[key] = now
                    intel_store.update_vessel_episode(
                        f"aisinc:{mmsi}:{kind}",
                        lat=lat,
                        lon=lon,
                        timestamp_utc=datetime.now(timezone.utc).isoformat(),
                        sog=sog,
                        nav_status=nav_status,
                        incident_lifecycle="active",
                    )
                return
            self._emitted[key] = now
            self._updated[key] = now

        # A nav-status report inside a known GNSS jamming zone reads very
        # differently from an isolated one: "not under command" next to
        # active jamming is far more likely a real navigation failure than
        # the usual benign cause. Best-effort — the jamming layer may be
        # empty (no recent data) and always returns 0.0 in that case, same
        # threshold (0.3) core/mda/watch.py uses for "worth flagging".
        jam_score = 0.0
        try:
            from core.mda.jamming import jamming as _jamming

            jam_score = _jamming.in_jamming_zone(lat, lon)
        except Exception:
            pass
        in_jamming_zone = jam_score >= 0.3

        plain_label = _KIND_LABEL.get(kind, kind.replace('_', ' '))
        title = plain_label
        if name:
            title += f" — {name}"
        text = f"{name or 'Vessel'} (MMSI {mmsi}): {plain_label.lower()}, reported via AIS."
        # Explicit, reproducible reasoning — the exact rule and values that
        # fired, not just the resulting label. Anyone can check this against
        # the thresholds in this file's own _INCIDENT_STATUS table.
        rule_reason = None
        if reports is not None and sustained_s is not None:
            rule_reason = (
                f"Flagged after {reports} report(s) over {sustained_s}s "
                f"(rule: ≥{min_reports} reports and ≥{int(min_span_s)}s sustained)."
            )
            text += f" {rule_reason}"
        if in_jamming_zone:
            text += " Position falls inside a known GNSS jamming zone — treat this as a stronger signal than an isolated report."
        event = IntelEvent(
            id=f"aisinc:{mmsi}:{kind}",
            type="distress" if is_distress else "vessel_incident",
            severity=severity,
            lat=lat,
            lon=lon,
            title=title[:200],
            text=text,
            url=f"https://www.marinetraffic.com/en/ais/details/ships/mmsi:{mmsi}",
            source=source,
            linked_mmsi=mmsi,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            metadata={
                "source_policy": "official_api",
                "transport": "ais_stream",
                "verification_status": "ais_transponder",
                "is_distress": is_distress,
                "publication_status": "published" if auto_publish else "internal",
                "maritime_domain": (
                    "grey_zone" if kind == "not_under_command"
                    else "safety" if kind == "aground"
                    else "sar"
                ),
                "report_kind": "distress" if is_distress else "vessel_incident",
                "coordinate_source": "ais_position",
                "location_uncertainty_m": 300,
                # A beacon rides a liferaft/person; a grounding is the ship.
                "case_type": "distress_sar" if kind == "distress_beacon" else "vessel_incident",
                "ais_nav_status_kind": kind,
                "vessel_name": name or None,
                "episode_update_count": 1,
                "first_observed_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
                "last_observed_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
                "observed_track": [{
                    "lon": round(float(lon), 6),
                    "lat": round(float(lat), 6),
                    "ts": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
                    **({"sog": round(float(sog), 2)} if sog is not None else {}),
                    **({"nav_status": int(nav_status)} if nav_status is not None else {}),
                }],
                "drift_eligible": kind in {"not_under_command", "disabled", "adrift"},
                "drift_event_id": f"intel:aisinc:{mmsi}:{kind}",
                "drift_vessel_type": "cargo",
                "jamming_score": round(jam_score, 2),
                "in_jamming_zone": in_jamming_zone,
                **({"detection_reason": rule_reason} if rule_reason else {}),
            },
        )
        if intel_store.add(event, dedup_key=f"aisinc:{mmsi}:{kind}"):
            logger.warning(
                "vessel incident: %s mmsi=%s at %.4f,%.4f (publish=%s)",
                kind, mmsi, lat, lon, auto_publish,
            )

    def _prune(self, now: float) -> None:
        self._last_prune = now
        with self._lock:
            self._episodes = {
                m: e for m, e in self._episodes.items()
                if now - e["first_seen"] < _STATE_TTL_S
            }
            self._emitted = {
                k: t for k, t in self._emitted.items() if now - t < _EMIT_COOLDOWN_S * 2
            }
            self._updated = {
                k: t for k, t in self._updated.items() if now - t < _EMIT_COOLDOWN_S * 2
            }


vessel_incident_monitor = VesselIncidentMonitor()
