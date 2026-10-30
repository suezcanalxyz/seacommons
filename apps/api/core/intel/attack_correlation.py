# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical, pure assessment of maritime attack reports against AIS evidence.

SourceObservation is the ingestion envelope; this module only assesses claims.
It never writes a database row, attributes an attacker, or publishes to LIVE.
In particular, a missing AIS sample is not evidence of jamming or an attack.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence


@dataclass(frozen=True)
class AttackReport:
    source_id: str
    source_url: str
    source_name: str
    # The original reporting chain, NOT the republisher's domain.
    # Unknown origin is deliberately ineligible for independent corroboration.
    origin_group: str | None
    occurred_at: datetime
    published_at: datetime
    received_at: datetime
    claim: str
    mmsi: str | None = None
    imo: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_uncertainty_nm: float = 0.0


@dataclass(frozen=True)
class AISPosition:
    mmsi: str
    observed_at: datetime
    latitude: float
    longitude: float
    imo: str | None = None


_ATTACK_CLAIMS = frozenset({"attack", "strike", "projectile_impact", "boarding_attack"})
_CONTEXT_CLAIMS = frozenset({"advisory", "risk", "near_miss", "suspicious_activity"})


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("All timestamps must have an explicit UTC offset")
    return value.astimezone(timezone.utc)


def _valid_identity(mmsi: str | None, imo: str | None) -> None:
    if mmsi is not None and (len(mmsi) != 9 or not mmsi.isdigit()):
        raise ValueError("MMSI must contain exactly nine digits")
    if imo is not None and (len(imo) != 7 or not imo.isdigit()):
        raise ValueError("IMO must contain exactly seven digits")


def _distance_nm(a: float, b: float, c: float, d: float) -> float:
    for lat, lon in ((a, b), (c, d)):
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Invalid geographic coordinates")
    delta_lat = math.radians(c - a)
    delta_lon = math.radians(d - b)
    x = (math.sin(delta_lat / 2) ** 2 +
         math.cos(math.radians(a)) * math.cos(math.radians(c)) *
         math.sin(delta_lon / 2) ** 2)
    return 3440.065 * 2 * math.asin(min(1.0, math.sqrt(max(0.0, x))))


def assess_maritime_attack(
    reports: Sequence[AttackReport],
    positions: Sequence[AISPosition],
    *,
    vessel_mmsi: str,
    vessel_imo: str | None = None,
    max_time_offset_minutes: int = 120,
    max_distance_nm: float = 30.0,
    max_report_span_minutes: int = 180,
) -> dict:
    """Return a review candidate, never an automatically published incident.

    Independent corroboration counts original reporting chains. A wire-service
    rewrite and the original government press release are one lineage if the
    wire report only repeats that press release.
    """
    _valid_identity(vessel_mmsi, vessel_imo)
    if not reports:
        return {"classification": "no_report", "publication_allowed": False}
    if max_time_offset_minutes < 0 or max_distance_nm < 0:
        raise ValueError("Matching thresholds must be non-negative")

    reasons: list[str] = []
    contradictions: list[str] = []
    compatible: list[AttackReport] = []
    seen_source_ids: set[tuple[str, str]] = set()
    for report in reports:
        _valid_identity(report.mmsi, report.imo)
        event = _utc(report.occurred_at)
        published = _utc(report.published_at)
        received = _utc(report.received_at)
        if received < published:
            contradictions.append("publication_after_receipt")
        if report.mmsi and report.mmsi != vessel_mmsi:
            contradictions.append("mmsi_conflict")
            continue
        if report.imo and vessel_imo and report.imo != vessel_imo:
            contradictions.append("imo_conflict")
            continue
        if report.claim in _CONTEXT_CLAIMS or report.claim not in _ATTACK_CLAIMS:
            continue
        if not report.mmsi and not report.imo:
            # Geography alone cannot identify a vessel.
            continue
        if report.imo and not vessel_imo and not report.mmsi:
            # IMO cannot be verified when the vessel registry has no IMO.
            continue
        key = (report.source_name, report.source_id)
        if key in seen_source_ids:
            continue
        seen_source_ids.add(key)
        if report.latitude is not None or report.longitude is not None:
            if report.latitude is None or report.longitude is None:
                contradictions.append("incomplete_report_coordinates")
                continue
            _distance_nm(report.latitude, report.longitude,
                         report.latitude, report.longitude)
        compatible.append(report)

    if compatible:
        start = min(_utc(r.occurred_at) for r in compatible)
        end = max(_utc(r.occurred_at) for r in compatible)
        if (end - start).total_seconds() > max_report_span_minutes * 60:
            contradictions.append("reports_outside_same_incident_window")
    else:
        start = end = None

    # Only an explicitly identified original source chain can corroborate.
    roots = sorted({r.origin_group.strip().lower() for r in compatible
                    if r.origin_group and r.origin_group.strip()})
    independently_corroborated = len(roots) >= 2
    if compatible:
        reasons.append("explicit_vessel_identity_in_report")
    if independently_corroborated:
        reasons.append("two_independent_original_reporting_chains")

    spatial_matches: list[tuple[float, float]] = []
    temporal_matches = 0
    for report in compatible:
        event = _utc(report.occurred_at)
        for position in positions:
            _valid_identity(position.mmsi, position.imo)
            if position.mmsi != vessel_mmsi:
                continue
            if vessel_imo and position.imo and position.imo != vessel_imo:
                continue
            offset = abs((_utc(position.observed_at) - event).total_seconds()) / 60
            if offset > max_time_offset_minutes:
                continue
            temporal_matches += 1
            if report.latitude is None or report.longitude is None:
                continue
            distance = _distance_nm(report.latitude, report.longitude,
                                    position.latitude, position.longitude)
            if distance <= max_distance_nm + max(0.0, report.location_uncertainty_nm):
                spatial_matches.append((distance, offset))
    if temporal_matches:
        reasons.append("ais_position_near_reported_time")
    if spatial_matches:
        reasons.append("ais_position_compatible_with_reported_location")

    blocking = any(c in {"mmsi_conflict", "imo_conflict",
                          "reports_outside_same_incident_window",
                          "publication_after_receipt"} for c in contradictions)
    if blocking:
        classification = "conflicting_evidence"
    elif independently_corroborated:
        classification = "corroborated_report_candidate"
    elif compatible:
        classification = "possible_attack_candidate"
    else:
        classification = "unlinked"

    lineage = sorted((r.source_name, r.source_id, r.source_url,
                      r.origin_group or "") for r in compatible)
    digest = hashlib.sha256(json.dumps(
        [vessel_mmsi, vessel_imo, lineage], sort_keys=True).encode()).hexdigest()[:20]
    return {
        "candidate_id": f"attack:{digest}",
        "classification": classification,
        "vessel_mmsi": vessel_mmsi,
        "vessel_imo": vessel_imo,
        "event_window_start": start.isoformat() if start else None,
        "event_window_end": end.isoformat() if end else None,
        "independent_origin_groups": roots,
        "independently_corroborated": independently_corroborated,
        "ais_temporal_match": bool(temporal_matches),
        "ais_spatial_match": bool(spatial_matches),
        "closest_ais_distance_nm": min((d for d, _ in spatial_matches), default=None),
        "source_lineage": [
            {"source_name": r.source_name, "source_id": r.source_id,
             "url": r.source_url, "origin_group": r.origin_group,
             "occurred_at": _utc(r.occurred_at).isoformat(),
             "published_at": _utc(r.published_at).isoformat(),
             "received_at": _utc(r.received_at).isoformat()}
            for r in compatible
        ],
        "reasons": reasons,
        "contradictions": sorted(set(contradictions)),
        "attacker": None,
        "ais_gap_proves_attack": False,
        "publication_allowed": False,
        "requires_operator_review": True,
    }
