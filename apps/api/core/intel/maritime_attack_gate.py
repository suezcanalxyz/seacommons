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
        if not item.source_url.startswith(("https://", "http://")) or not item.independent_group:
            reasons.append("missing_provenance")
            continue
        if published < event or received < published:
            reasons.append("chronology_requires_review")
        if item.position is not None and (not -90 <= item.position[0] <= 90 or not -180 <= item.position[1] <= 180):
            reasons.append("invalid_position")
            continue
        valid.append((item, event))
    claims = [(item, at) for item, at in valid if item.explicit_attack_claim and not item.signal_only]
    compatible = []
    for item, at in claims:
        if compatible:
            anchor, anchor_at = compatible[0]
            if abs((at-anchor_at).total_seconds()) > max_hours*3600:
                reasons.append("time_mismatch")
                continue
            if anchor.imo and item.imo and anchor.imo != item.imo:
                reasons.append("imo_conflict")
                continue
            if anchor.mmsi and item.mmsi and anchor.mmsi != item.mmsi:
                reasons.append("mmsi_conflict")
                continue
            if anchor.position and item.position and _distance_km(anchor.position, item.position) > max_km + max(0, anchor.uncertainty_km) + max(0, item.uncertainty_km):
                reasons.append("spatial_mismatch")
                continue
        compatible.append((item, at))
    groups = sorted({item.independent_group for item, _ in compatible})
    if len(groups) < 2:
        reasons.append("fewer_than_two_independent_attack_claims")
    return {
        "status": "candidate_for_analyst_review" if len(groups) >= 2 else "insufficient_evidence",
        "reasons": sorted(set(reasons)),
        "independent_groups": groups,
        "sources": [{"id": i.source_id, "url": i.source_url, "event_at": i.event_at,
                     "published_at": i.published_at, "received_at": i.received_at}
                    for i, _ in valid],
        "automatic_publication": False,
        "attribution": None,
    }
