# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure, conservative AIS-to-reported-attack correlation. No database writes.

A gap is supporting evidence, never proof of an attack. A corroborated report
requires two independent source groups and vessel identity matching.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt

@dataclass(frozen=True)
class AttackReport:
    vessel_mmsi: str | None
    vessel_imo: str | None
    occurred_at: datetime
    latitude: float | None
    longitude: float | None
    independent_sources: tuple[str, ...]
    source_urls: tuple[str, ...] = ()
    received_at: datetime | None = None
    position_uncertainty_nm: float = 0.0

@dataclass(frozen=True)
class AISGap:
    mmsi: str
    last_seen: datetime
    next_seen: datetime
    latitude: float
    longitude: float
    observed_samples: int = 0
    coverage_verified: bool = False

def _utc(t: datetime) -> datetime:
    if t.tzinfo is None:
        raise ValueError('timestamps must include timezone')
    return t.astimezone(timezone.utc)

def _distance_nm(a: float, b: float, c: float, d: float) -> float:
    x = sin(radians(c-a)/2)**2 + cos(radians(a))*cos(radians(c))*sin(radians(d-b)/2)**2
    return 3440.065 * 2 * asin(min(1.0,sqrt(x)))

def correlate_attack(report: AttackReport, gap: AISGap, *, known_imo: str | None = None,
                     max_distance_nm: float = 30.0, max_offset_minutes: int = 90) -> dict:
    """Return review-ready assessment, never an automatically published incident."""
    same_mmsi = bool(report.vessel_mmsi and report.vessel_mmsi == gap.mmsi)
    same_imo = bool(report.vessel_imo and known_imo and report.vessel_imo == known_imo)
    identity = same_mmsi or same_imo
    start, end, event = map(_utc, (gap.last_seen, gap.next_seen, report.occurred_at))
    if end <= start:
        raise ValueError('invalid AIS gap')
    offset = (start-event).total_seconds()/60 if event < start else ((event-end).total_seconds()/60 if event > end else 0)
    temporal = abs(offset) <= max_offset_minutes
    distance = None
    if report.latitude is not None and report.longitude is not None:
        distance = _distance_nm(gap.latitude, gap.longitude, report.latitude, report.longitude)
    spatial = distance is not None and distance <= max_distance_nm + max(0.0, report.position_uncertainty_nm)
    corroborated = len({s.strip().lower() for s in report.independent_sources if s.strip()}) >= 2
    candidate = identity and temporal and spatial
    # Missing AIS positions in our database do not prove a radio outage.
    verified_gap = bool(gap.coverage_verified and gap.observed_samples > 0)
    return {'identity_match':identity,'temporal_match':temporal,'spatial_match':spatial,
            'distance_nm':distance,'offset_minutes':offset,'independently_corroborated':corroborated,
            'ais_coverage_verified':verified_gap,'ais_gap_evidence_only':True,
            'source_urls':report.source_urls,
            'reported_at':event.isoformat(),
            'received_at':_utc(report.received_at).isoformat() if report.received_at else None,
            'classification':('corroborated_attack_candidate' if candidate and corroborated else
                              'possible_attack_candidate' if candidate else 'unlinked'),
            'publication_allowed':False,'requires_operator_review':True}

@dataclass(frozen=True)
class AISFix:
    """Observed AIS position; absence of a gap is not a negative attack test."""
    mmsi: str
    observed_at: datetime
    latitude: float
    longitude: float


def correlate_report_to_track(
    report: AttackReport, fixes: tuple[AISFix, ...], *, known_imo: str | None = None,
    max_distance_nm: float = 30.0, max_offset_minutes: int = 90,
) -> dict:
    """News-first candidate ranking, independent of gap detection.

    The caller supplies verified *independence groups*, not publisher counts.
    No automated result authorizes publication or attacker attribution.
    """
    event = _utc(report.occurred_at)
    # Named vessel but no independently reported coordinates: identity/time
    # match is reviewable, not a verified geospatial attack correlation.
    if report.latitude is None or report.longitude is None:
        identified = [f for f in fixes if (
            (report.vessel_mmsi and f.mmsi == report.vessel_mmsi)
            or (report.vessel_imo and known_imo and report.vessel_imo == known_imo)
        ) and abs((_utc(f.observed_at)-event).total_seconds()) <= max_offset_minutes*60]
        return {'classification': 'identity_time_candidate' if identified else 'unlinked',
                'matching_positions': len(identified), 'geospatial_verified': False,
                'publication_allowed': False, 'requires_operator_review': True,
                'ais_gap_required': False, 'source_urls': report.source_urls}
    candidates = []
    for fix in fixes:
        delta = abs((_utc(fix.observed_at) - event).total_seconds()) / 60
        if delta > max_offset_minutes:
            continue
        distance = None
        if report.latitude is not None and report.longitude is not None:
            distance = _distance_nm(fix.latitude, fix.longitude,
                                    report.latitude, report.longitude)
        if distance is None or distance > max_distance_nm + max(0, report.position_uncertainty_nm):
            continue
        identity = bool(
            (report.vessel_mmsi and report.vessel_mmsi == fix.mmsi)
            or (report.vessel_imo and known_imo and report.vessel_imo == known_imo)
        )
        candidates.append((not identity, delta, distance, fix, identity))
    if not candidates:
        return {'classification': 'unlinked', 'publication_allowed': False,
                'requires_operator_review': True, 'matching_positions': 0}
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    _, delta, distance, best, identity = candidates[0]
    groups = {s.strip().lower() for s in report.independent_sources if s.strip()}
    return {
        'classification': ('corroborated_attack_candidate' if identity and len(groups) >= 2
                           else 'possible_attack_candidate' if identity
                           else 'spatial_candidate_identity_unresolved'),
        'mmsi': best.mmsi, 'identity_match': identity,
        'distance_nm': round(distance, 3), 'offset_minutes': round(delta, 3),
        'matching_positions': len(candidates),
        'independently_corroborated': len(groups) >= 2,
        'source_urls': report.source_urls,
        'publication_allowed': False, 'requires_operator_review': True,
        'ais_gap_required': False,
    }
