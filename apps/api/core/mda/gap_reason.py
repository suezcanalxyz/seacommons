# SPDX-License-Identifier: AGPL-3.0-or-later
"""AIS gap reason-code feature (docs/fixes.md M4.3).

M4.3's exit gate, verbatim: "synthetic/common port outage produces no
intentional-dark hypothesis; genuine isolated gap fixture remains
detectable independent of vessel class."

``build_gap_reason()`` is the decision this module exists to make, and it
satisfies "independent of vessel class" by construction: there is no
``vessel_type`` parameter anywhere in this module. It reuses
``core.intel.ais_integrity_replay.classify_gap`` (docs/fixes.md M4.1) as
the actual vessel-gap-vs-coverage-gap decision -- already built and
scored against ``ais_integrity.jsonl``'s exact port-outage/isolated-gap
fixtures -- rather than inventing a second copy of that reasoning here.
This module's job is only to assemble the M4.3 reason_components feature
(gap_duration, expected_messages, coverage_ratio, neighbour_message_ratio,
pre_gap_course/speed, post_gap_reappearance, coast_distance,
jamming_context) from a caller-supplied ``core.mda.coverage.CoverageBaseline``
(docs/fixes.md M4.2) plus the gap-specific inputs classify_gap() needs.

Standalone and read-only, same as coverage.py and ais_integrity_replay.py:
NOT wired into core.mda.watch.scan_gaps() yet. That live-detector wiring
-- replacing scan_gaps()'s hard ship_type 30-32/36-37/52/60-69 exclusions
with a call through this module -- is intentionally left as a distinct,
final follow-up PR: swapping a production security detector's actual
behaviour deserves its own dedicated review, separate from landing the
(already fully tested) decision logic itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.intel.ais_integrity_replay import classify_gap
from core.mda.coverage import CoverageBaseline


@dataclass(frozen=True)
class GapReason:
    hypothesis: str  # "vessel_gap" | "coverage_gap" | "not_alertable"
    confidence: float
    gap_duration_s: float
    expected_messages: Optional[int]
    coverage_ratio: float
    neighbour_message_ratio: Optional[float]
    pre_gap_course: Optional[float]
    pre_gap_speed: Optional[float]
    post_gap_reappearance: Optional[bool]
    coast_distance_km: Optional[float]
    jamming_context: Optional[float]


def build_gap_reason(
    *,
    gap_duration_s: float,
    nearby_vessels_reporting_before: int,
    nearby_vessels_reporting_after: int,
    coverage: CoverageBaseline,
    pre_gap_course: Optional[float] = None,
    pre_gap_speed: Optional[float] = None,
    post_gap_reappearance: Optional[bool] = None,
) -> GapReason:
    """Deliberately takes no vessel_type/ship_type parameter -- see module
    docstring. A caller with vessel-type information keeps it as separate
    context alongside whatever this returns; it never influences the
    hypothesis or confidence computed here.
    """
    coverage_ratio = (
        nearby_vessels_reporting_after / nearby_vessels_reporting_before
        if nearby_vessels_reporting_before else 0.0
    )
    hypothesis, confidence = classify_gap(
        silence_duration_min=gap_duration_s / 60.0,
        nearby_vessels_reporting_before=nearby_vessels_reporting_before,
        nearby_vessels_reporting_after=nearby_vessels_reporting_after,
        local_reporting_ratio=coverage_ratio,
    )

    expected_messages = None
    if coverage.expected_reporting_interval_s:
        expected_messages = int(gap_duration_s // coverage.expected_reporting_interval_s)

    return GapReason(
        hypothesis=hypothesis,
        confidence=confidence,
        gap_duration_s=gap_duration_s,
        expected_messages=expected_messages,
        coverage_ratio=coverage_ratio,
        neighbour_message_ratio=coverage.neighbour_message_ratio,
        pre_gap_course=pre_gap_course,
        pre_gap_speed=pre_gap_speed,
        post_gap_reappearance=post_gap_reappearance,
        coast_distance_km=coverage.coast_distance_km,
        jamming_context=coverage.jamming_context,
    )
