# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed, pure maritime attack evidence gate. No DB writes or publication."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt


def _time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Evidence timestamps must have timezone")
    return dt.astimezone(timezone.utc)


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


def evaluate_attack_candidate(
    evidence: list[AttackEvidence], *,
    max_hours: float = 12,
    max_km: float = 75,
) -> dict:
    """Only independent explicit claims can corroborate; AIS gaps never count."""
    reasons: list[str] = []
    if not evidence:
        return {"status": "insufficient_evidence", "reasons": ["no_evidence"], "sources": []}
    valid = []
    for item in evidence:
        try:
            event, published, received = (_time(t) for t in (item.event_at, item.published_at, item.received_at))
        except (ValueError, TypeError):
            reasons.append("invalid_timestamp")
            continue
        if not item.source_id or not item.source_url.startswith("https://") or not item.independent_group:
            reasons.append("missing_provenance")
            continue
        if published < event or received < published:
            reasons.append("chronology_requires_review")
            continue
        if item.uncertainty_km < 0 or (item.position is not None and (not -90 <= item.position[0] <= 90 or not -180 <= item.position[1] <= 180)):
            reasons.append("invalid_position")
            continue
        valid.append((item, event))
    claims = [(item, at) for item, at in valid if item.explicit_attack_claim and not item.signal_only]
    # Do not count duplicate source records as independent confirmations.
    unique_claims = []
    seen_sources = set()
    for item, at in claims:
        key = item.source_url.split("#", 1)[0].split("?", 1)[0].rstrip("/").lower()
        if key in seen_sources:
            reasons.append("duplicate_source")
            continue
        seen_sources.add(key)
        unique_claims.append((item, at))
    def matches(a, at_a, b, at_b):
        if abs((at_a-at_b).total_seconds()) > max_hours * 3600:
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
    groups = sorted({item.independent_group for item, _ in unique_claims})
    if len(groups) < 2:
        reasons.append("fewer_than_two_independent_attack_claims")
    return {
        "status": "candidate_for_analyst_review" if len(groups) >= 2 and not any(r in reasons for r in ("time_mismatch", "imo_conflict", "mmsi_conflict", "spatial_mismatch", "unresolved_vessel_identity")) else "insufficient_evidence",
        "reasons": sorted(set(reasons)),
        "independent_groups": groups,
        "sources": [{"id": i.source_id, "url": i.source_url, "event_at": i.event_at,
                     "published_at": i.published_at, "received_at": i.received_at}
                    for i, _ in valid],
        "automatic_publication": False,
        "attribution": None,
    }
