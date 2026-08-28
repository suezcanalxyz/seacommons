# SPDX-License-Identifier: AGPL-3.0-or-later
"""OSINT cross-source fusion — turns independent signals into correlated alerts.

Every intel event funnels through ``intel_store.add()``; this module subscribes
to that single fan-out point (``intel_store.subscribe``) and, for each new
positioned event, runs a small set of correlation rules against the recent
event window. A rule that fires:

  * emits a ``correlated_alert`` IntelEvent back through ``intel_store.add()``
    (so it reaches the map / feed / WebSocket / DB like any other event),
  * links the contributing events onto a case it auto-opens
    (``core.cases.service.open_case`` + ``case_intel_events``),
  * fires an outbound notification (``core.notifications.notify_alert``).

v1 rules:
  1. SAR multi-source     — reuses ``triangulation.evaluate`` (>=2 independent
     channels agree on a place/time) → domain ``sar``.
  2. Dark-fleet / spoofing — two distinct AIS anomalies for one MMSI inside a
     window → domain ``sanctions``.
  3. Grey-zone / infra    — an AIS gap/loiter close to offshore infrastructure
     → domain ``grey_zone``.

The engine is intentionally separate from ``core.anomaly.correlation`` (physical
sensor fusion); they share the weighting *pattern*, not the channels.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from core.config import config
from core.geo import cluster_key, haversine_km
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

ALERT_TYPE = "correlated_alert"

_AIS_KINDS = {"ais_anomaly", "ais_spike"}
_SPOOFING_ANOMALIES = {
    "dark_zone_entry", "impossible_speed", "position_jump",
    "gap", "long_gap", "zone_incursion", "ais_rendezvous", "sdn_match",
}
_GREY_ZONE_ANOMALIES = {"gap", "long_gap", "loiter", "dark_zone_entry", "cable_proximity"}

_DOMAIN_CASE_TYPE = {
    "sar": "distress_sar",
    "sanctions": "sanctions_watch",
    "grey_zone": "subsea_infrastructure",
    "safety": "vessel_incident",
    "piracy": "piracy_incident",
}

# A few subsea cable / pipeline corridors in the central + eastern Med, as
# ordered (lat, lon) waypoints. Distance is measured to the nearest segment.
_SUBSEA_CORRIDORS: list[tuple[str, list[tuple[float, float]]]] = [
    ("Melita-1 / Malta-Sicily", [(37.05, 14.50), (35.90, 14.45)]),
    ("Greenstream pipeline (Mellitah-Gela)", [(32.90, 13.30), (37.07, 14.25)]),
    ("EllaLink / IMEWE Sicily approach", [(37.50, 15.10), (36.70, 15.60)]),
    ("SEA-ME-WE Egypt landing (Alexandria)", [(31.20, 29.90), (33.40, 30.60)]),
]


@dataclass
class FusionSignal:
    event_id: str
    kind: str
    anomaly_type: str
    lat: float
    lon: float
    ts: float  # epoch seconds
    mmsi: str = ""
    imo: str = ""
    source: str = ""
    severity: str = ""
    weight: float = 0.0


@dataclass
class FusedAlert:
    alert_type: str
    domain: str
    severity: str
    confidence: float
    lat: float
    lon: float
    ts: float
    contributing_event_ids: list[str]
    contributing_sources: list[str]
    summary: str
    open_case: bool = True
    case_type: str = "unspecified"
    vessel_mmsi: str = ""
    cluster_id: str = field(default="")

    def __post_init__(self) -> None:
        if self.cluster_id:
            return
        # Prefer an identity that is stable no matter which signal of the set
        # triggered the rule (so two near-simultaneous evaluations of the same
        # incident collapse to one alert): the sorted contributing event ids,
        # else a coarse place/time bucket.
        if self.contributing_event_ids:
            key = ",".join(sorted(self.contributing_event_ids))
        else:
            key = cluster_key(self.lat, self.lon, self.ts)
        self.cluster_id = f"{self.alert_type}:{key}"


# ── timestamps ────────────────────────────────────────────────────────────────

def _epoch(value: str) -> float:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).timestamp()


# ── normalisation ─────────────────────────────────────────────────────────────

def normalize(event: IntelEvent) -> Optional[FusionSignal]:
    """Project an IntelEvent onto the fields the rules need. None → skip."""
    if event.type == ALERT_TYPE:
        return None  # never correlate an alert with itself
    if event.lat is None or event.lon is None:
        return None
    meta = event.metadata or {}
    anomaly_type = str(
        meta.get("anomaly_type")
        or meta.get("spike_type")
        or meta.get("subtype")
        or meta.get("ais_nav_status_kind")
        or ""
    ).lower()
    mmsi = str(event.linked_mmsi or meta.get("mmsi") or meta.get("MMSI") or "").strip()
    imo = str(meta.get("imo") or meta.get("IMO") or "").strip()
    return FusionSignal(
        event_id=event.id,
        kind=event.type,
        anomaly_type=anomaly_type,
        lat=float(event.lat),
        lon=float(event.lon),
        ts=_epoch(event.timestamp_utc),
        mmsi=mmsi,
        imo=imo,
        source=event.source or event.type,
        severity=event.severity or "",
    )


def _recent_signals(exclude_id: str, limit: int = 600) -> list[FusionSignal]:
    out: list[FusionSignal] = []
    for candidate in intel_store.events(limit=limit):
        if candidate.id == exclude_id:
            continue
        sig = normalize(candidate)
        if sig is not None:
            out.append(sig)
    return out


# ── rules ─────────────────────────────────────────────────────────────────────

def _rule_sar_multisource(new: FusionSignal, event: IntelEvent) -> Optional[FusedAlert]:
    from core.intel import triangulation

    summary = triangulation.evaluate(event)
    if not summary:
        return None
    confidence = float(summary.get("corroboration_confidence") or 0.0)
    sources = list(summary.get("corroborating_sources") or [])
    ids = list(summary.get("corroborating_event_ids") or [event.id])
    return FusedAlert(
        alert_type="sar_corroborated",
        domain="sar",
        severity="high",
        confidence=round(confidence, 3),
        lat=new.lat, lon=new.lon, ts=new.ts,
        contributing_event_ids=ids,
        contributing_sources=sources,
        summary="Multi-source SAR corroboration: " + ", ".join(sources),
        case_type="distress_sar",
    )


def _rule_spoofing(new: FusionSignal, event: IntelEvent) -> Optional[FusedAlert]:
    if new.kind not in _AIS_KINDS or not new.mmsi:
        return None
    if new.anomaly_type not in _SPOOFING_ANOMALIES:
        return None
    window = config.FUSION_SPOOFING_WINDOW_S
    radius = config.FUSION_SPOOFING_RADIUS_KM
    for other in _recent_signals(new.event_id):
        if other.kind not in _AIS_KINDS or other.mmsi != new.mmsi:
            continue
        if other.anomaly_type not in _SPOOFING_ANOMALIES:
            continue
        if other.anomaly_type == new.anomaly_type:
            continue  # need two *distinct* kinds of evidence
        if abs(other.ts - new.ts) > window:
            continue
        if haversine_km(new.lat, new.lon, other.lat, other.lon) > radius:
            continue
        evidence = {new.anomaly_type, other.anomaly_type}
        confidence = round(min(0.95, 0.45 + 0.2 * len(evidence)), 3)
        return FusedAlert(
            alert_type="spoofing",
            domain="sanctions",
            severity="high",
            confidence=confidence,
            lat=new.lat, lon=new.lon, ts=new.ts,
            contributing_event_ids=[new.event_id, other.event_id],
            contributing_sources=sorted({new.source, other.source}),
            summary=(
                f"MMSI {new.mmsi}: {other.anomaly_type} + {new.anomaly_type} "
                f"within {int(window // 3600)}h"
            ),
            case_type="sanctions_watch",
            vessel_mmsi=new.mmsi,
        )
    return None


def _nearest_infrastructure(lat: float, lon: float, max_km: float) -> Optional[dict]:
    """Nearest subsea cable / pipeline / platform, from the MDA reference index
    (real geometry from EMODnet / submarinecablemap, with a bundled fallback)."""
    try:
        from core.mda.reference import reference

        hit = reference.nearest_infrastructure(lat, lon, max_km=max_km)
        if hit is not None:
            return {"name": f"{hit.name} ({hit.kind})", "distance_km": hit.distance_km,
                    "kind": hit.kind}
    except Exception:  # pragma: no cover - fall back to the bundled corridors
        pass
    best: Optional[dict] = None
    for name, waypoints in _SUBSEA_CORRIDORS:
        for i in range(len(waypoints) - 1):
            dist = _point_to_segment_km(lat, lon, waypoints[i], waypoints[i + 1])
            if dist <= max_km and (best is None or dist < best["distance_km"]):
                best = {"name": name, "distance_km": dist}
    return best


def _point_to_segment_km(lat: float, lon: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    """Approximate distance from a point to a short segment (planar, Med-scale)."""
    ax, ay = a[1], a[0]
    bx, by = b[1], b[0]
    px, py = lon, lat
    abx, aby = bx - ax, by - ay
    denom = abx * abx + aby * aby
    t = 0.0 if denom == 0 else max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / denom))
    cx, cy = ax + t * abx, ay + t * aby
    return haversine_km(lat, lon, cy, cx)


def _rule_grey_zone(new: FusionSignal, event: IntelEvent) -> Optional[FusedAlert]:
    if new.kind not in _AIS_KINDS:
        return None
    if new.anomaly_type not in _GREY_ZONE_ANOMALIES:
        return None
    hit = _nearest_infrastructure(new.lat, new.lon, config.FUSION_INFRA_PROXIMITY_KM)
    if hit is None:
        return None
    return FusedAlert(
        alert_type="infra_proximity",
        domain="grey_zone",
        severity="medium",
        confidence=round(max(0.4, 0.75 - hit["distance_km"] / 40.0), 3),
        lat=new.lat, lon=new.lon, ts=new.ts,
        contributing_event_ids=[new.event_id],
        contributing_sources=[new.source],
        summary=f"AIS {new.anomaly_type} within {hit['distance_km']:.1f} km of {hit['name']}",
        case_type="subsea_infrastructure",
        vessel_mmsi=new.mmsi,
    )


_GROUNDING_SUBTYPES = {"aground", "grounding", "not_under_command", "disabled", "adrift"}


def _rule_single_source(new: FusionSignal, event: IntelEvent) -> Optional[FusedAlert]:
    """Sources with no correlation partner still need a case: a serious vessel
    incident, or a high-severity maritime natural-hazard alert near the AOI.
    """
    from core.intel.landmask import in_operational_region

    if not in_operational_region(new.lat, new.lon):
        return None

    if new.kind == "vessel_incident" and new.anomaly_type in _GROUNDING_SUBTYPES:
        return FusedAlert(
            alert_type="vessel_casualty",
            domain="safety",
            severity=new.severity or "high",
            confidence=0.7,
            lat=new.lat, lon=new.lon, ts=new.ts,
            contributing_event_ids=[new.event_id],
            contributing_sources=[new.source],
            summary=f"Vessel incident: {new.anomaly_type or 'casualty'} — {event.title[:120]}",
            case_type="vessel_incident",
            vessel_mmsi=new.mmsi,
        )

    if new.kind == "gdacs" and new.severity in {"high", "critical"}:
        return FusedAlert(
            alert_type="natural_hazard",
            domain="safety",
            severity=new.severity,
            confidence=0.55,
            lat=new.lat, lon=new.lon, ts=new.ts,
            contributing_event_ids=[new.event_id],
            contributing_sources=[new.source],
            summary=f"GDACS {new.severity} hazard near the operational area — {event.title[:120]}",
            open_case=False,
            case_type="monitoring",
        )
    return None


_RULES: list[Callable[[FusionSignal, IntelEvent], Optional[FusedAlert]]] = [
    _rule_sar_multisource,
    _rule_spoofing,
    _rule_grey_zone,
    _rule_single_source,
]


# ── emission ──────────────────────────────────────────────────────────────────

_EMIT_LOCK = threading.Lock()


def _already_alerted(cluster_id: str) -> bool:
    for existing in intel_store.events(limit=300):
        if existing.type == ALERT_TYPE and existing.metadata.get("cluster_id") == cluster_id:
            return True
    return False


def _emit(alert: FusedAlert) -> None:
    with _EMIT_LOCK:
        _emit_locked(alert)


def _emit_locked(alert: FusedAlert) -> None:
    if _already_alerted(alert.cluster_id):
        logger.debug("fusion: cluster %s already alerted, skipping", alert.cluster_id)
        return

    metadata = {
        "alert_type": alert.alert_type,
        "maritime_domain": alert.domain,
        "confidence": alert.confidence,
        "contributing": alert.contributing_event_ids,
        "contributing_sources": alert.contributing_sources,
        "cluster_id": alert.cluster_id,
        "is_distress": alert.domain == "sar",
        "verification_status": "multi_source_corroborated",
        "coordinate_source": "post_text",
    }
    if alert.vessel_mmsi:
        metadata["mmsi"] = alert.vessel_mmsi
    alert_event = IntelEvent(
        type=ALERT_TYPE,
        severity=alert.severity,
        lat=alert.lat,
        lon=alert.lon,
        title=alert.summary[:255],
        text=alert.summary[:600],
        source="SeaCommons fusion",
        linked_mmsi=alert.vessel_mmsi,
        metadata=metadata,
    )
    added = intel_store.add(alert_event, dedup_key=f"fusion:{alert.cluster_id}")
    if not added:
        return
    logger.warning(
        "FUSION ALERT %s [%s] confidence=%.2f sources=%s",
        alert.alert_type, alert.domain, alert.confidence, alert.contributing_sources,
    )

    case_id = None
    if alert.open_case:
        case_id = _open_case_for_alert(alert, alert_event.id)
        if case_id:
            intel_store.update_metadata(alert_event.id, metadata={"case_id": case_id})

    payload = {
        "id": alert_event.id, "alert_type": alert.alert_type, "domain": alert.domain,
        "confidence": alert.confidence, "lat": alert.lat, "lon": alert.lon,
        "contributing_sources": alert.contributing_sources, "cluster_id": alert.cluster_id,
        "case_id": case_id,
    }
    try:
        from core.notifications import notify_alert

        notify_alert(payload)
    except Exception as exc:  # pragma: no cover
        logger.warning("fusion: notify_alert failed: %s", exc)


def _open_case_for_alert(alert: FusedAlert, alert_event_id: str) -> Optional[str]:
    try:
        from core.cases.service import OPEN_STATUSES, open_case
        from core.db.models import CaseDB, CaseIntelEventDB
        from core.db.session import session_scope

        linked_ids = list(dict.fromkeys([alert_event_id, *alert.contributing_event_ids]))
        with session_scope() as db:
            existing = (
                db.query(CaseIntelEventDB.case_id)
                .join(CaseDB, CaseDB.case_id == CaseIntelEventDB.case_id)
                .filter(CaseIntelEventDB.event_id.in_([i[:32] for i in linked_ids]))
                .filter(CaseDB.status.in_(OPEN_STATUSES))
                .first()
            )
            if existing is not None:
                logger.info("fusion: open case %s already covers cluster %s", existing[0], alert.cluster_id)
                return existing[0]
            priority = "critical" if alert.confidence >= 0.8 else "high"
            case = open_case(
                db,
                title=f"[{alert.domain}] {alert.alert_type}: {alert.summary}"[:256],
                created_by="fusion-engine",
                case_type=_DOMAIN_CASE_TYPE.get(alert.domain, alert.case_type),
                priority=priority,
                sensitivity="restricted",
                summary=alert.summary,
                lat=alert.lat,
                lon=alert.lon,
                intel_event_ids=linked_ids,
                timeline_note=f"Auto-opened by fusion engine ({alert.alert_type})",
                audit_action="case.auto_created",
                audit_data={"alert_type": alert.alert_type, "cluster_id": alert.cluster_id},
                notify=False,  # _emit() sends a richer, cooldown-guarded notify_alert
            )
            return case["case_id"]
    except Exception as exc:
        logger.warning("fusion: auto-case failed: %s", exc)
        return None


# ── entry point ───────────────────────────────────────────────────────────────

def evaluate(event: IntelEvent) -> None:
    """intel_store subscriber — safe to call for every event."""
    if not getattr(config, "FUSION_ENABLED", True):
        return
    signal = normalize(event)
    if signal is None:
        return
    if signal.kind == "ais_anomaly" and _CORRELATION_ENGINE is not None:
        try:
            _CORRELATION_ENGINE.ingest("ais:anomalies", {
                "anomaly_type": signal.anomaly_type,
                "mmsi": signal.mmsi,
                "position": {"lat": signal.lat, "lon": signal.lon, "alt": 0, "source": "ais"},
                "confidence": 0.6,
            })
        except Exception as exc:  # pragma: no cover
            logger.debug("fusion: correlation-engine ingest skipped: %s", exc)
    for rule in _RULES:
        try:
            alert = rule(signal, event)
        except Exception as exc:  # pragma: no cover - one rule must not break others
            logger.warning("fusion rule %s failed: %s", rule.__name__, exc)
            continue
        if alert is not None:
            _emit(alert)


_REGISTERED = False
_CORRELATION_ENGINE = None


def set_correlation_engine(engine) -> None:
    """Give the fusion engine a handle to the physical-sensor CorrelationEngine
    so AIS anomalies can also feed its channel map (see core.anomaly.correlation).
    """
    global _CORRELATION_ENGINE
    _CORRELATION_ENGINE = engine


def emit_physical_threat(threat: dict) -> None:
    """on_threat callback for CorrelationEngine — surface a sensor-fusion threat
    as a correlated_alert IntelEvent so it reaches the map / feed / notifications.
    """
    classification = str(threat.get("classification") or "physical_threat_candidate")
    domain = "sanctions" if classification == "vessel_spoofing_confirmed" else "safety"
    sensor_data = threat.get("sensor_data") or {}
    position = (sensor_data.get("ais_anomaly") or {}).get("position") or {}
    lat, lon = position.get("lat"), position.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or (lat == 0 and lon == 0):
        logger.info("fusion: physical threat %s has no position, not mapped", classification)
        return
    ts = datetime.now(timezone.utc).timestamp()
    alert = FusedAlert(
        alert_type=classification,
        domain=domain,
        severity="critical" if threat.get("urgent") else "high",
        confidence=round(float(threat.get("confidence") or 0.0), 3),
        lat=float(lat), lon=float(lon), ts=ts,
        contributing_event_ids=[],
        contributing_sources=list(threat.get("sources") or []),
        summary=f"Sensor fusion: {classification} ({', '.join(threat.get('sources') or [])})",
        open_case=threat.get("urgent", False) or classification == "vessel_spoofing_confirmed",
        case_type=_DOMAIN_CASE_TYPE.get(domain, "unspecified"),
    )
    _emit(alert)


def register() -> None:
    """Wire the engine into the intel store. Idempotent."""
    global _REGISTERED
    if _REGISTERED:
        return
    intel_store.subscribe(evaluate)
    _REGISTERED = True
    logger.info("OSINT fusion engine registered (%d rules)", len(_RULES))
