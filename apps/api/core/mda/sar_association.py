# SPDX-License-Identifier: AGPL-3.0-or-later
"""SAR candidate association (docs/fixes.md M7.2).

"Association must use acquisition time. Propagate last reliable AIS state
to image time with uncertainty. ... Never emit 'dark vessel confirmed'
from one unmatched target."

``propagate_ais_state()`` projects a vessel's last reliable position
forward (or backward) to a satellite scene's acquisition time using its
course/speed, growing the position uncertainty with elapsed time --
matching how ``core.drift`` already treats a stale fix (a longer gap means
a wider search area, never a falsely precise point). ``associate_candidate()``
then compares an unidentified SAR detection against that propagated
position and returns exactly the M7.2 required stored fields, structured
so "dark vessel confirmed" is not a representable outcome: the result
type has no confirmed state at all, only a candidate association plus
its ``counter_candidates`` -- other, equally or more plausible
explanations for the same detection.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

ALGORITHM_VERSION = "sar_association/v0"

_NM_PER_DEGREE_LAT = 60.0405


@dataclass(frozen=True)
class PropagatedState:
    lat: float
    lon: float
    uncertainty_m: float
    elapsed_s: float


def propagate_ais_state(
    *,
    last_lat: float,
    last_lon: float,
    last_observed_at: datetime,
    target_time: datetime,
    course_deg: Optional[float] = None,
    speed_kn: Optional[float] = None,
    base_uncertainty_m: float = 150.0,
    growth_m_per_hour: float = 1852.0,  # 1 nm/h -- a conservative default drift-of-uncertainty rate
) -> PropagatedState:
    """Projects the last known position to ``target_time`` along
    ``course_deg``/``speed_kn`` when both are known; holds position
    unchanged (uncertainty still grows) when either is missing -- this
    never fabricates a heading/speed it wasn't given. Uncertainty always
    grows with elapsed time, in both temporal directions (a scene
    acquired before the last fix is exactly as uncertain as one acquired
    after it).
    """
    elapsed_s = (target_time - last_observed_at).total_seconds()
    elapsed_h = abs(elapsed_s) / 3600.0

    lat, lon = last_lat, last_lon
    if course_deg is not None and speed_kn is not None and speed_kn > 0:
        distance_nm = speed_kn * (elapsed_s / 3600.0)  # signed -- can project backward
        bearing = math.radians(course_deg)
        north_nm = math.cos(bearing) * distance_nm
        east_nm = math.sin(bearing) * distance_nm
        lat = last_lat + north_nm / _NM_PER_DEGREE_LAT
        lon_scale = max(0.2, math.cos(math.radians(last_lat)))
        lon = last_lon + east_nm / (_NM_PER_DEGREE_LAT * lon_scale)

    uncertainty_m = base_uncertainty_m + growth_m_per_hour * elapsed_h
    return PropagatedState(
        lat=round(lat, 5), lon=round(lon, 5),
        uncertainty_m=round(uncertainty_m, 1), elapsed_s=elapsed_s,
    )


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_m = 6_371_000.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return r_m * 2 * math.asin(math.sqrt(max(0.0, a)))


@dataclass(frozen=True)
class CounterCandidate:
    """A different, equally-considered explanation for the same SAR
    detection -- e.g. another vessel whose propagated position also lands
    near it, or a known non-vessel clutter source. Present so an
    association can never quietly stand as the only explanation offered."""

    label: str
    distance_to_predicted_area_m: float


@dataclass(frozen=True)
class SarAssociation:
    """The M7.2 required stored fields, verbatim. There is deliberately
    no ``confirmed``/``status`` field of any kind: this type has no
    representation for "dark vessel confirmed" at all -- only a scored
    candidate association plus whatever counter-candidates were checked
    alongside it. A caller building an InvestigationHypothesis
    (core.intel.hypothesis, M6) treats this as ONE piece of evidence
    toward the dark_transit gate, never as a verdict by itself.
    """

    scene_id: str
    acquired_at: datetime
    candidate_detection_id: str
    distance_to_predicted_area_m: float
    association_method: str
    association_confidence: float
    counter_candidates: tuple[CounterCandidate, ...] = field(default_factory=tuple)
    algorithm_version: str = ALGORITHM_VERSION


def associate_candidate(
    *,
    scene_id: str,
    acquired_at: datetime,
    candidate_detection_id: str,
    detection_lat: float,
    detection_lon: float,
    propagated: PropagatedState,
    counter_candidates: tuple[CounterCandidate, ...] = (),
    association_method: str = "propagated_ais_position",
) -> SarAssociation:
    """Distance-based confidence, bounded by the propagated position's own
    uncertainty: a detection within the uncertainty radius scores high,
    one several radii away scores low. Confidence is capped well short of
    1.0 -- this is always a candidate association, never a confirmation,
    regardless of how close the distance is (the exit gate holds even for
    a seemingly perfect match: a SAR detection at the exact propagated
    point could still be a different, unrelated vessel that happened to
    be there).
    """
    distance_m = _haversine_m(propagated.lat, propagated.lon, detection_lat, detection_lon)
    radii = distance_m / max(propagated.uncertainty_m, 1.0)
    confidence = max(0.0, min(0.75, 0.75 * math.exp(-radii)))
    return SarAssociation(
        scene_id=scene_id,
        acquired_at=acquired_at,
        candidate_detection_id=candidate_detection_id,
        distance_to_predicted_area_m=round(distance_m, 1),
        association_method=association_method,
        association_confidence=round(confidence, 3),
        counter_candidates=counter_candidates,
    )
