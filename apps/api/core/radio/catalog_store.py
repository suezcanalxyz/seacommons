from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from math import asin, cos, radians, sin, sqrt
from urllib.parse import urlsplit


class ReceiverComputedState(StrEnum):
    CATALOGUED = "catalogued"
    REVIEW_REQUIRED = "review_required"
    OFFLINE = "offline"
    STANDBY = "standby"
    ELIGIBLE = "eligible"
    ACTIVE = "active"


@dataclass(frozen=True)
class ReceiverScoreInput:
    distance_km: float | None
    reachable: bool
    supports_target: bool
    uptime_ratio: float
    failure_rate: float
    independent_lineage: bool
    license_class: str
    available_slots: int | None = None


def calculate_receiver_score(value: ReceiverScoreInput) -> float:
    distance_component = 0.0
    if value.distance_km is not None:
        distance_component = max(0.0, 30.0 * (1.0 - min(value.distance_km, 1500.0) / 1500.0))
    score = distance_component
    score += 20.0 if value.reachable else 0.0
    score += 15.0 if value.supports_target else 0.0
    score += 15.0 * max(0.0, min(value.uptime_ratio, 1.0))
    score += 8.0 if value.independent_lineage else 0.0
    score += 7.0 if value.license_class == "open_source" else 3.0
    if value.available_slots is not None and value.available_slots > 0:
        score += min(5.0, float(value.available_slots))
    score -= 20.0 * max(0.0, min(value.failure_rate, 1.0))
    return round(max(0.0, min(score, 100.0)), 2)


def recompute_receiver_state(*, terms_status: str, reachable: bool,
                             supports_target: bool, score: float) -> ReceiverComputedState:
    if terms_status != "allowed":
        return ReceiverComputedState.REVIEW_REQUIRED
    if not reachable:
        return ReceiverComputedState.OFFLINE
    if not supports_target:
        return ReceiverComputedState.STANDBY
    if score >= 50.0:
        return ReceiverComputedState.ELIGIBLE
    return ReceiverComputedState.STANDBY


def persist_discovered_receivers(rows) -> int:
    from core.db.models import ReceiverCatalogDB
    from core.db.session import session_scope

    changed = 0
    with session_scope() as db:
        for row in rows:
            saved = db.query(ReceiverCatalogDB).filter_by(discovery_key=row.discovery_key).one_or_none()
            if saved is None:
                saved = ReceiverCatalogDB(
                    discovery_key=row.discovery_key,
                    public_label=row.public_label[:128],
                    network_family=row.network_family,
                    endpoint=row.endpoint,
                    directory_source=row.directory_source,
                    license_class="open_source" if row.network_family == "openwebrx" else "public_access",
                    terms_status=row.terms_status,
                    activation_status=row.activation_status,
                )
                db.add(saved)
                changed += 1
            else:
                saved.public_label = row.public_label[:128]
                saved.directory_source = row.directory_source
                saved.last_discovered_at = datetime.now(timezone.utc)
    return changed

_ZONE_CENTERS = {
    "central_med": (35.9, 14.4),
    "sicily_channel": (36.3, 13.2),
    "malta": (35.9, 14.4),
    "tunisia_north": (36.8, 10.2),
    "ionian": (37.5, 19.5),
}


def _distance_km(lat: float, lon: float, zone: str) -> float:
    b_lat, b_lon = _ZONE_CENTERS.get(zone, _ZONE_CENTERS["central_med"])
    dlat, dlon = radians(b_lat - lat), radians(b_lon - lon)
    value = sin(dlat / 2) ** 2 + cos(radians(lat)) * cos(radians(b_lat)) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(value))


def _supports(capabilities, frequency_hz: int) -> bool:
    for cap in capabilities or ():
        lo = cap.get("min_hz") if isinstance(cap, dict) else None
        hi = cap.get("max_hz") if isinstance(cap, dict) else None
        if lo is not None and hi is not None and int(lo) <= frequency_hz <= int(hi):
            return True
    return False


def _default_probe(row) -> dict[str, object]:
    from urllib.request import Request, urlopen
    try:
        request = Request(row.endpoint, headers={"User-Agent": "SeaCommons/1.0 receiver-health"})
        with urlopen(request, timeout=3) as response:
            reachable = 200 <= int(getattr(response, "status", 200)) < 500
        return {"reachable": reachable, "available_slots": None}
    except Exception:
        return {"reachable": False, "available_slots": None}


def probe_and_score_catalog(*, zone: str = "central_med",
                            target_frequency_hz: int = 2_187_500,
                            probe=_default_probe,
                            limit: int = 500) -> dict[str, int]:
    from core.db.models import ReceiverCatalogDB
    from core.db.session import session_scope

    counts = {state.value: 0 for state in ReceiverComputedState}
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        rows = db.query(ReceiverCatalogDB).order_by(ReceiverCatalogDB.score.desc()).limit(limit).all()
        for row in rows:
            result = dict(probe(row) or {})
            reachable = bool(result.get("reachable"))
            slots = result.get("available_slots")
            row.reachable = reachable
            row.available_slots = int(slots) if isinstance(slots, int) else None
            row.uptime_ratio = round(float(row.uptime_ratio or 0.0) * 0.8 + (0.2 if reachable else 0.0), 4)
            row.failure_rate = round(float(row.failure_rate or 0.0) * 0.8 + (0.0 if reachable else 0.2), 4)
            supports_target = _supports(row.capabilities, target_frequency_hz)
            distance = None
            if row.lat is not None and row.lon is not None:
                distance = _distance_km(float(row.lat), float(row.lon), zone)
            score = calculate_receiver_score(ReceiverScoreInput(
                distance_km=distance, reachable=reachable,
                supports_target=supports_target,
                uptime_ratio=float(row.uptime_ratio or 0.0),
                failure_rate=float(row.failure_rate or 0.0),
                independent_lineage=bool(row.physical_lineage),
                license_class=str(row.license_class or "public_access"),
                available_slots=row.available_slots,
            ))
            row.score = score
            state = recompute_receiver_state(
                terms_status=row.terms_status,
                reachable=reachable,
                supports_target=supports_target,
                score=score,
            )
            row.activation_status = state.value
            row.last_probed_at = now
            row.updated_at = now
            counts[state.value] += 1
    return counts


def _discovery_key(network_family: str, endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    host = (parsed.hostname or "").lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{network_family}:{host}:{port}"


def persist_curated_catalog() -> int:
    from core.db.models import ReceiverCatalogDB
    from core.db.session import session_scope
    from core.radio.catalog import catalog_entries

    now = datetime.now(timezone.utc)
    changed = 0
    with session_scope() as db:
        for entry in catalog_entries():
            key = _discovery_key(entry.network_family, entry.endpoint)
            row = db.query(ReceiverCatalogDB).filter_by(discovery_key=key).one_or_none()
            if row is None:
                row = ReceiverCatalogDB(discovery_key=key)
                db.add(row)
                changed += 1
            row.receiver_id = entry.receiver_id
            row.public_label = entry.public_label
            row.network_family = entry.network_family
            row.physical_lineage = entry.physical_lineage
            row.endpoint = entry.endpoint
            row.directory_source = "curated_seed"
            row.license_class = entry.license_class
            row.source_terms = entry.source_terms
            row.terms_status = entry.terms_status
            row.activation_status = entry.activation_status
            row.country = entry.country
            row.lat = entry.lat
            row.lon = entry.lon
            row.capabilities = [
                {
                    "min_hz": cap.frequency_min_hz,
                    "max_hz": cap.frequency_max_hz,
                    "modes": list(cap.modes),
                }
                for cap in entry.capabilities
            ]
            row.last_discovered_at = now
            row.updated_at = now
    return changed


def rank_persistent_catalog(*, target_frequency_hz: int, mode: str,
                            limit: int = 16):
    from core.db.models import ReceiverCatalogDB
    from core.db.session import session_scope
    from core.radio.provider import ReceiverCapability
    from core.radio.registry import ReceiverDescriptor

    result = []
    seen: set[str] = set()
    with session_scope() as db:
        rows = (
            db.query(ReceiverCatalogDB)
            .filter_by(terms_status="allowed", activation_status="eligible", reachable=True)
            .order_by(ReceiverCatalogDB.score.desc())
            .limit(max(limit * 3, limit))
            .all()
        )
        for row in rows:
            if not row.receiver_id or not row.physical_lineage or not row.source_terms:
                continue
            if row.physical_lineage in seen:
                continue
            caps = []
            for cap in row.capabilities or ():
                if not isinstance(cap, dict):
                    continue
                modes = tuple(str(item).lower() for item in cap.get("modes", ()))
                lo, hi = cap.get("min_hz"), cap.get("max_hz")
                if lo is None or hi is None:
                    continue
                if not int(lo) <= target_frequency_hz <= int(hi) or mode.lower() not in modes:
                    continue
                caps.append(ReceiverCapability(int(lo), int(hi), modes))
            if not caps:
                continue
            result.append(ReceiverDescriptor(
                receiver_id=row.receiver_id, provider=row.network_family,
                frontend_url=row.endpoint, physical_lineage=row.physical_lineage,
                enabled=True, terms_status="allowed", source_terms=row.source_terms,
                capabilities=tuple(caps), public_label=row.public_label,
                channel_kind="monitor", frequency_hz=target_frequency_hz, mode=mode,
            ))
            seen.add(row.physical_lineage)
            if len(result) >= limit:
                break
    return tuple(result)


def public_catalog_summary(*, limit: int = 16) -> dict[str, object]:
    from core.db.models import ReceiverCatalogDB
    from core.db.session import session_scope

    with session_scope() as db:
        rows = db.query(ReceiverCatalogDB).order_by(ReceiverCatalogDB.score.desc()).all()
        top = rows[: max(1, min(limit, 64))]
        return {
            "catalogued": len(rows),
            "reachable": sum(1 for row in rows if row.reachable is True),
            "review_required": sum(1 for row in rows if row.terms_status != "allowed"),
            "eligible": sum(1 for row in rows if row.activation_status == "eligible"),
            "offline": sum(1 for row in rows if row.activation_status == "offline"),
            "receivers": [
                {
                    "receiver_id": row.receiver_id,
                    "station_label": row.public_label,
                    "network_family": row.network_family,
                    "country": row.country,
                    "state": row.activation_status,
                    "score": round(float(row.score or 0.0), 2),
                }
                for row in top
            ],
        }
