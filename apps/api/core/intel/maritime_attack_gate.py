# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed, pure maritime attack evidence gate. No DB writes or publication."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, isfinite, radians, sin, sqrt
from urllib.parse import urlsplit


def _time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Evidence timestamp must be an ISO-8601 string")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Evidence timestamps must have timezone")
    return dt.astimezone(timezone.utc)


def _valid_imo(value: str) -> bool:
    """Seven-digit IMO number with the standard weighted check digit."""
    return (isinstance(value, str) and len(value) == 7 and value.isascii() and value.isdigit()
            and sum(int(digit) * weight for digit, weight in zip(value[:6], range(7, 1, -1))) % 10 == int(value[-1]))


def _valid_mmsi(value: str) -> bool:
    return isinstance(value, str) and len(value) == 9 and value.isascii() and value.isdigit()


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    h = sin(radians(lat2-lat1)/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(radians(lon2-lon1)/2)**2
    return 12742 * asin(min(1, sqrt(h)))


@dataclass(frozen=True)
class AttackEvidence:
    source_id: str
    independent_group: str
    source_url: str
    event_at: str
    published_at: str
    received_at: str
    imo: str | None = None
    mmsi: str | None = None
    position: tuple[float, float] | None = None
    uncertainty_km: float = 0
    explicit_attack_claim: bool = False
    signal_only: bool = False
    primary_origin_id: str | None = None  # shared upstream release/report, not publisher
    event_uncertainty_minutes: float = 0  # bounded observation-time uncertainty, not publication latency
    position_provenance: str = "unspecified"  # ais_observed | documentary_estimate | coastal_reference | model_estimate


def evaluate_attack_candidate(
    evidence: list[AttackEvidence], *,
    max_hours: float = 12,
    max_km: float = 75,
) -> dict:
    """Only independent explicit claims can corroborate; AIS gaps never count."""
    reasons: list[str] = []
    if not evidence:
        return {"status": "insufficient_evidence", "reasons": ["no_evidence"], "sources": [], "rejected_evidence": [], "independent_groups": [], "automatic_publication": False, "attribution": None}
    if not all(type(value) in (int, float) and isfinite(value) and value >= 0 for value in (max_hours, max_km)):
        return {"status": "insufficient_evidence", "reasons": ["invalid_matching_threshold"], "sources": [], "rejected_evidence": [], "independent_groups": [], "automatic_publication": False, "attribution": None}
    valid = []
    rejected_evidence: list[dict[str, str]] = []
    for item in evidence:
        try:
            event, published, received = (_time(t) for t in (item.event_at, item.published_at, item.received_at))
        except (ValueError, TypeError):
            reasons.append("invalid_timestamp")
            rejected_evidence.append({"source_id": item.source_id if isinstance(item.source_id, str) else "", "reason": "invalid_timestamp"})
            continue
        try:
            url = urlsplit(item.source_url.strip()) if isinstance(item.source_url, str) else None
            host = url.hostname if url is not None else None
            port = url.port if url is not None else None  # triggers validation of malformed ports
        except ValueError:
            url, host = None, None
        if (not isinstance(item.source_id, str) or not item.source_id.strip() or
                not isinstance(item.independent_group, str) or not item.independent_group.strip() or
                url is None or url.scheme != "https" or not host or
                url.username is not None or url.password is not None or
                any(ch.isspace() for ch in item.source_url) or
                (host is not None and (host.startswith(".") or host.endswith(".")))):
            reasons.append("missing_provenance")
            rejected_evidence.append({"source_id": item.source_id if isinstance(item.source_id, str) else "", "reason": "missing_provenance"})
            continue
        if published < event or received < published:
            reasons.append("chronology_requires_review")
            rejected_evidence.append({"source_id": item.source_id if isinstance(item.source_id, str) else "", "reason": "chronology_requires_review"})
            continue
        if (type(item.event_uncertainty_minutes) not in (int, float) or
                not isfinite(item.event_uncertainty_minutes) or
                not 0 <= item.event_uncertainty_minutes <= 180):
            reasons.append("invalid_time_uncertainty")
            rejected_evidence.append({"source_id": item.source_id if isinstance(item.source_id, str) else "", "reason": "invalid_time_uncertainty"})
            continue
        # Boolean coordinates and unbounded error circles are not measurements.
        # Reject excessive uncertainty rather than letting it bridge unrelated seas.
        if (isinstance(item.uncertainty_km, bool) or
                not isinstance(item.uncertainty_km, (int, float)) or
                not isfinite(item.uncertainty_km) or
                item.uncertainty_km < 0 or item.uncertainty_km > max_km or
                (item.position is not None and (
                    not isinstance(item.position, (tuple, list)) or len(item.position) != 2 or
                    any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
                        for v in item.position) or
                    not -90 <= item.position[0] <= 90 or
                    not -180 <= item.position[1] <= 180))):
            reasons.append("invalid_position")
            rejected_evidence.append({"source_id": item.source_id if isinstance(item.source_id, str) else "", "reason": "invalid_position"})
            continue
        # Preserve how a location was obtained; estimated locations are not AIS fixes.
        if (item.position_provenance not in (
                "unspecified", "ais_observed", "documentary_estimate",
                "coastal_reference", "model_estimate") or
                (item.position is None and item.position_provenance != "unspecified")):
            reasons.append("invalid_position_provenance")
            rejected_evidence.append({"source_id": item.source_id if isinstance(item.source_id, str) else "", "reason": "invalid_position_provenance"})
            continue
        if ((item.imo is not None and not _valid_imo(item.imo)) or
                (item.mmsi is not None and not _valid_mmsi(item.mmsi))):
            reasons.append("invalid_vessel_identifier")
            rejected_evidence.append({"source_id": item.source_id if isinstance(item.source_id, str) else "", "reason": "invalid_vessel_identifier"})
            continue
        # A publisher is not necessarily an independent primary source.
        # Unknown origin cannot contribute to two-source corroboration.
        if item.explicit_attack_claim and not item.signal_only and (
                not isinstance(item.primary_origin_id, str) or
                not item.primary_origin_id.strip()):
            reasons.append("unverified_primary_origin")
            rejected_evidence.append({"source_id": item.source_id if isinstance(item.source_id, str) else "", "reason": "unverified_primary_origin"})
            continue
        valid.append((item, event))
    claims = [(item, at) for item, at in valid if item.explicit_attack_claim and not item.signal_only]
    # Do not count duplicate source records as independent confirmations.
    unique_claims = []
    seen_sources = set()
    seen_ids = set()
    seen_origins = set()
    for item, at in claims:
        key = item.source_url.split("#", 1)[0].split("?", 1)[0].rstrip("/").lower()
        origin = (item.primary_origin_id or '').strip().casefold()
        if key in seen_sources or item.source_id.strip().casefold() in seen_ids or (origin and origin in seen_origins):
            reasons.append("duplicate_source")
            continue
        seen_sources.add(key)
        seen_ids.add(item.source_id.strip().casefold())
        if origin:
            seen_origins.add(origin)
        unique_claims.append((item, at))
    def matches(a, at_a, b, at_b):
        if abs((at_a-at_b).total_seconds()) > (max_hours * 60 + a.event_uncertainty_minutes + b.event_uncertainty_minutes) * 60:
            return False, "time_mismatch"
        if a.imo and b.imo and a.imo != b.imo:
            return False, "imo_conflict"
        if not ((a.imo and b.imo and a.imo == b.imo) or (a.mmsi and b.mmsi and a.mmsi == b.mmsi)):
            return False, "unresolved_vessel_identity"
        if a.mmsi and b.mmsi and a.mmsi != b.mmsi:
            return False, "mmsi_conflict"
        if a.position and b.position and _distance_km(a.position, b.position) > max_km + max(0, a.uncertainty_km) + max(0, b.uncertainty_km):
            return False, "spatial_mismatch"
        return True, None

    # Fail closed on contradictory claims: an input-order-dependent subset
    # must never become a corroborated incident.
    for index, (item, at) in enumerate(unique_claims):
        for other, other_at in unique_claims[index + 1:]:
            ok, reason = matches(item, at, other, other_at)
            if not ok and reason:
                reasons.append(reason)
    groups = sorted({item.independent_group.strip().casefold() for item, _ in unique_claims})
    if len(groups) < 2:
        reasons.append("fewer_than_two_independent_attack_claims")
    # Invalid or contradictory submitted evidence requires manual remediation.
    # Never promote a clean-looking subset while discarding problematic claims.
    return {
        "status": "candidate_for_analyst_review" if len(groups) >= 2 and not reasons else "insufficient_evidence",
        "reasons": sorted(set(reasons)),
        "independent_groups": groups,
        "rejected_evidence": rejected_evidence,
        "sources": [{"id": i.source_id, "url": i.source_url, "event_at": i.event_at,
                     "published_at": i.published_at, "received_at": i.received_at,
                     "imo": i.imo, "mmsi": i.mmsi,
                     "position": list(i.position) if i.position is not None else None,
                     "uncertainty_km": i.uncertainty_km,
                     "position_provenance": i.position_provenance,
                     "event_uncertainty_minutes": i.event_uncertainty_minutes,
                     "independent_group": i.independent_group,
                     "explicit_attack_claim": i.explicit_attack_claim,
                     "signal_only": i.signal_only,
                     "primary_origin_id": i.primary_origin_id}
                    for i, _ in valid],
        "automatic_publication": False,
        "attribution": None,
    }
