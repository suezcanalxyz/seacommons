# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure, conservative maritime incident correlation (staging prototype).

No database writes, publication, scheduled execution, or AIS-based attack
inference. An AIS gap is context, NEVER proof of an attack. Independent
lineage groups must reflect the ORIGINAL reporting authority, not merely
different outlets republishing the same announcement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Sequence


@dataclass(frozen=True)
class VesselRef:
    imo: str = ""
    mmsi: str = ""
    name: str = ""


@dataclass(frozen=True)
class IncidentClaim:
    claim_id: str
    kind: str
    occurred_at: datetime
    source_group: str
    source_url: str
    vessel: VesselRef
    lat: float | None = None
    lon: float | None = None
    uncertainty_km: float = 0.0
    published_at: datetime | None = None
    received_at: datetime | None = None
    # The originating document/case identifier, shared by syndicated copies.
    # A publisher URL is not sufficient proof of independent reporting.
    origin_report_id: str | None = None
    # Precision of reported event time, not ingestion latency.
    time_uncertainty_minutes: float = 0.0


@dataclass(frozen=True)
class AISFix:
    mmsi: str
    observed_at: datetime
    lat: float
    lon: float


@dataclass(frozen=True)
class AISGap:
    mmsi: str
    observed_at: datetime
    event_id: str


@dataclass(frozen=True)
class Correlation:
    status: str  # no_match | candidate | corroborated
    incident_type: str
    color_token: str
    claim_ids: tuple[str, ...]
    independent_groups: tuple[str, ...]
    supporting: tuple[str, ...]
    contradicting: tuple[str, ...]
    nearest_ais_km: float | None = None
    nearest_ais_minutes: float | None = None
    related_gap_ids: tuple[str, ...] = ()
    # Provenance is retained even when the claim is only a review candidate.
    source_evidence: tuple[dict[str, str | None], ...] = ()
    publication_allowed: bool = False
    requires_operator_review: bool = True


_KINDS = frozenset({"attack", "sinking", "explosion", "collision", "piracy"})
_COLORS = {
    "candidate": "maritime_incident_candidate_orange",
    "attack": "maritime_attack_red",
    "sinking": "maritime_sinking_bordeaux",
    "other": "maritime_incident_red",
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamps must include timezone")
    return value.astimezone(timezone.utc)


def _name(value: str) -> str:
    return "".join(char for char in value.upper() if char.isalnum())


def _identity_match(subject: VesselRef, reported: VesselRef) -> str:
    """An explicit contradictory IMO/MMSI is a veto, even when names match."""
    if subject.imo and reported.imo and subject.imo != reported.imo:
        return "conflict"
    if subject.mmsi and reported.mmsi and subject.mmsi != reported.mmsi:
        return "conflict"
    if subject.imo and reported.imo and subject.imo == reported.imo:
        return "strong"
    if subject.mmsi and reported.mmsi and subject.mmsi == reported.mmsi:
        return "strong"
    if subject.name and reported.name and _name(subject.name) == _name(reported.name):
        return "weak"
    return "unknown"


def _km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    dlat, dlon = radians(b_lat - a_lat), radians(b_lon - a_lon)
    h = sin(dlat / 2) ** 2 + cos(radians(a_lat)) * cos(radians(b_lat)) * sin(dlon / 2) ** 2
    return 12742.0 * asin(min(1.0, sqrt(h)))


def correlate(
    subject: VesselRef,
    claims: Sequence[IncidentClaim],
    ais_fixes: Sequence[AISFix] = (),
    ais_gaps: Sequence[AISGap] = (),
) -> Correlation:
    """Correlate one claimed incident without promoting or mutating PLAY.

    Separate attacks and sinkings are separate claims/episodes. A single
    official report is still a candidate under the two-lineage rule.
    """
    if not claims:
        return Correlation("no_match", "", "", (), (), (), ("no_incident_claim",))
    anchor = claims[0]
    if anchor.kind not in _KINDS:
        raise ValueError("Unsupported maritime incident kind")
    if anchor.uncertainty_km < 0 or anchor.time_uncertainty_minutes < 0:
        raise ValueError("Negative incident uncertainty")
    _utc(anchor.occurred_at)
    if _identity_match(subject, anchor.vessel) in {"conflict", "unknown"}:
        return Correlation("no_match", anchor.kind, "", (), (), (), ("anchor_identity_conflict",))
    valid: list[IncidentClaim] = []
    strong_identity = False
    contradictions: list[str] = []
    seen_ids: set[str] = set()

    for claim in claims:
        if claim.claim_id in seen_ids:
            continue
        seen_ids.add(claim.claim_id)
        if claim.kind != anchor.kind:
            contradictions.append("different_incident_kind:" + claim.claim_id)
            continue
        if claim.published_at is not None:
            published = _utc(claim.published_at)
            if claim.received_at is not None:
                received = _utc(claim.received_at)
                if (published - received).total_seconds() > 300:
                    contradictions.append("publication_after_receipt:" + claim.claim_id)
                    continue
        if claim.uncertainty_km < 0 or claim.time_uncertainty_minutes < 0:
            raise ValueError("Negative incident uncertainty")
        delta_minutes = abs((_utc(claim.occurred_at) - _utc(anchor.occurred_at)).total_seconds()) / 60
        # Separate attacks hours apart must not collapse into one episode.
        max_minutes = 360 if anchor.kind == "sinking" else 90
        if delta_minutes > max_minutes + anchor.time_uncertainty_minutes + claim.time_uncertainty_minutes:
            contradictions.append("temporal_conflict:" + claim.claim_id)
            continue
        identity = _identity_match(subject, claim.vessel)
        if identity in {"conflict", "unknown"}:
            contradictions.append("identity_" + identity + ":" + claim.claim_id)
            continue
        if (anchor.lat is not None and anchor.lon is not None
                and claim.lat is not None and claim.lon is not None):
            distance = _km(anchor.lat, anchor.lon, claim.lat, claim.lon)
            if distance > 35.0 + anchor.uncertainty_km + claim.uncertainty_km:
                contradictions.append("spatial_conflict:" + claim.claim_id)
                continue
        strong_identity |= identity == "strong"
        valid.append(claim)

    if not valid:
        return Correlation("no_match", anchor.kind, "", (), (), (), tuple(contradictions))
    # Corroboration requires an EXPLICIT original document/case identifier.
    # Source names and URLs alone do not establish editorial independence.
    # A single document cannot count twice even if different origins are
    # accidentally assigned to the same URL, or if it is syndicated.
    groups_by_origin: dict[str, str] = {}
    seen_document_urls: set[str] = set()
    for claim in valid:
        origin = (claim.origin_report_id or "").strip()
        if not origin or not claim.source_url or claim.source_url in seen_document_urls:
            continue
        seen_document_urls.add(claim.source_url)
        groups_by_origin.setdefault(origin, claim.source_group.strip())
    groups = tuple(sorted({group for group in groups_by_origin.values() if group}))
    has_urls = all(claim.source_url.startswith("https://") for claim in valid)
    corroborated = len(groups) >= 2 and strong_identity and has_urls
    status = "corroborated" if corroborated else "candidate"
    color = (_COLORS.get(anchor.kind, _COLORS["other"]) if corroborated else _COLORS["candidate"])
    support = ["incident_claim", "vessel_identity_matched"]
    if strong_identity:
        support.append("strong_vessel_identifier")
    if len(groups) >= 2:
        support.append("independent_source_groups")

    nearest: tuple[float, float] | None = None
    if subject.mmsi:
        for claim in valid:
            if claim.lat is None or claim.lon is None:
                continue
            for fix in ais_fixes:
                if fix.mmsi != subject.mmsi:
                    continue
                minutes = abs((_utc(fix.observed_at) - _utc(claim.occurred_at)).total_seconds()) / 60
                if minutes > 120:
                    continue
                distance = _km(fix.lat, fix.lon, claim.lat, claim.lon)
                if distance > 30 + claim.uncertainty_km:
                    continue
                if nearest is None or (minutes, distance) < (nearest[1], nearest[0]):
                    nearest = (distance, minutes)
    # Contradictory AIS is not proof an attack did not occur: it may be
    # spoofed or replayed. Flag it and require human review instead.
    ais_spatial_conflict = False
    if subject.mmsi:
        for claim in valid:
            if claim.lat is None or claim.lon is None:
                continue
            for fix in ais_fixes:
                if fix.mmsi != subject.mmsi:
                    continue
                offset = abs((_utc(fix.observed_at) - _utc(claim.occurred_at)).total_seconds()) / 60
                if offset <= 30 + claim.time_uncertainty_minutes:
                    if _km(fix.lat, fix.lon, claim.lat, claim.lon) > 100 + claim.uncertainty_km:
                        ais_spatial_conflict = True
    if ais_spatial_conflict:
        contradictions.append("ais_position_conflict_needs_review")
        status = "candidate"
        color = _COLORS["candidate"]
    if nearest is not None:
        support.append("ais_spatiotemporal_context_not_attack_proof")

    # Gap signals only add context if temporally proximate; never upgrade status.
    gap_ids = tuple(sorted({
        gap.event_id for gap in ais_gaps
        if gap.mmsi == subject.mmsi
        and abs((_utc(gap.observed_at) - _utc(anchor.occurred_at)).total_seconds()) <= 6 * 3600
    }))
    if gap_ids:
        support.append("proximate_ais_gap_context_not_attack_proof")
    return Correlation(
        status, anchor.kind, color,
        tuple(claim.claim_id for claim in valid), groups,
        tuple(support), tuple(contradictions),
        nearest[0] if nearest else None,
        nearest[1] if nearest else None,
        gap_ids,
        tuple({
            "claim_id": claim.claim_id,
            "source_url": claim.source_url,
            "source_group": claim.source_group,
            "origin_report_id": claim.origin_report_id,
            "time_uncertainty_minutes": str(claim.time_uncertainty_minutes),
            "occurred_at": _utc(claim.occurred_at).isoformat(),
            "published_at": (_utc(claim.published_at).isoformat()
                             if claim.published_at is not None else None),
            "received_at": (_utc(claim.received_at).isoformat()
                            if claim.received_at is not None else None),
        } for claim in valid),
    )
