# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured humanitarian incident assessment (docs/fixes.md M2).

``core.intel.humanitarian.humanitarian_case_metadata`` -- the ingestion
write path -- stays exactly as-is; this module does not replace it or any
existing write path yet. It is an additional, typed read produced from the
same raw text, built around the one rule the flat V1 metadata could not
express: multiple quantities in one post are separate facts, never folded
into one number. "50 aboard, 20 rescued, 3 missing" must stay three
distinct ``PeopleCounts`` fields, not a single ``persons=50``.

``assess()`` reuses the SAME deterministic classifiers the rest of the
codebase already uses for case_type/distress/resolution (docs/prompt.md
sec 3: no second taxonomy) -- it does not reimplement or fork them.

v0 scope: ``needs``, ``actors``, ``location_claims``, ``temporal_claims``
and ``resolution_evidence`` are reserved fields on ``HumanitarianAssessment``
(present so callers can already type against the full M2 schema) but are
not yet populated -- extracting those is a follow-up PR, same "smallest
slice" pattern used for the M1.2 adapters. ``lifecycle`` here is the
TEXT-STATED outcome only (active/resolved/needs_review); the fourth value,
``archived``, is a time-based transition this module cannot see from text
alone and stays exactly where it already lives, ``core.intel.lifecycle``.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from core.domain.live_contracts import HumanitarianCaseType, IncidentLifecycle
from core.intel.geoextract import (
    is_direct_distress_call,
    is_ongoing_incident,
    is_resolved_distress,
)
from core.intel.humanitarian import _case_type

_APPROX_MARKER_RE = re.compile(r"~|≈|\babout\b|\baround\b|\bapprox\.?\b|\bcirca\b", re.I)

# Same multilingual "people" noun set as core.intel.humanitarian._PEOPLE
# (Alarm Phone posts the same alert in several languages) -- optional filler
# between the count and the role marker, e.g. "30 personnes à bord" vs
# "30 à bord".
_QTY = (
    r"(\d{1,4})\s*"
    r"(?:(?:people|persons|passengers|migrants|survivors"
    r"|personnes?|passagers?|rescapée?s?"
    r"|persone|passeggeri"
    r"|personas?|pasajeros?"
    r"|menschen|personen)\s*)?"
)

_ROLE_PATTERNS: dict[str, re.Pattern[str]] = {
    "aboard": re.compile(
        _QTY + r"(?:on\s*board|aboard|à\s*bord|a\s*bordo|an\s*Bord)\b", re.I,
    ),
    "rescued": re.compile(
        _QTY + r"(?:rescued|saved|sauvés?|sauvées?|salvati|salvate|rescatados?|rescatadas?|gerettet)\b",
        re.I,
    ),
    "missing": re.compile(
        _QTY + r"(?:missing|disparus?|disparues?|dispersi|disperse|desaparecidos?|desaparecidas?|vermisst)\b",
        re.I,
    ),
    "dead": re.compile(
        _QTY + r"(?:dead|died|killed|morts?|mortes?|morti|morte|muertos?|muertas?|\btot\b|gestorben)\b",
        re.I,
    ),
    "injured": re.compile(
        _QTY + r"(?:injured|wounded|blessés?|blessées?|feriti|ferite|heridos?|heridas?|verletzt)\b",
        re.I,
    ),
    "intercepted": re.compile(
        _QTY + r"(?:intercepted|interceptés?|interceptées?|intercettati|intercettate|interceptados?|interceptadas?)\b",
        re.I,
    ),
    "returned": re.compile(
        _QTY + r"(?:returned|pushed\s*back|renvoyés?|renvoyées?|rimpatriati|rimpatriate|devueltos?|devueltas?)\b",
        re.I,
    ),
}

_VESSEL_TYPE_RE = re.compile(
    r"\b(rubber\s*boat|dinghy|wooden\s*boat|fibreglass\s*boat|iron\s*boat|zodiac)\b", re.I,
)
_ENGINE_STATUS_RE = re.compile(
    r"\b(engine\s*failure|no\s*engine|engine\s*stopped|panne\s*moteur)\b", re.I,
)
_VESSEL_CONDITION_RE = re.compile(
    r"\b(taking\s*on\s*water|overloaded|capsiz\w*|sinking|adrift)\b", re.I,
)


@dataclass(frozen=True)
class PeopleCounts:
    aboard: Optional[int] = None
    rescued: Optional[int] = None
    missing: Optional[int] = None
    dead: Optional[int] = None
    injured: Optional[int] = None
    intercepted: Optional[int] = None
    returned: Optional[int] = None


@dataclass(frozen=True)
class VesselInfo:
    type_reported: Optional[str] = None
    condition: Optional[str] = None
    engine_status: Optional[str] = None


@dataclass(frozen=True)
class HumanitarianAssessment:
    case_type: str
    lifecycle: str
    is_operational: bool
    publication_recommendation: str
    confidence: float
    confidence_basis: list[str] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    people: PeopleCounts = field(default_factory=PeopleCounts)
    vessel: VesselInfo = field(default_factory=VesselInfo)
    needs: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    location_claims: list[str] = field(default_factory=list)
    temporal_claims: list[str] = field(default_factory=list)
    resolution_evidence: list[str] = field(default_factory=list)


def _extract_people(text: str) -> PeopleCounts:
    values: dict[str, Optional[int]] = {}
    for role, pattern in _ROLE_PATTERNS.items():
        match = pattern.search(text)
        values[role] = int(match.group(1)) if match else None
    return PeopleCounts(**values)


def _extract_vessel(text: str) -> VesselInfo:
    type_match = _VESSEL_TYPE_RE.search(text)
    condition_match = _VESSEL_CONDITION_RE.search(text)
    engine_match = _ENGINE_STATUS_RE.search(text)
    return VesselInfo(
        type_reported=type_match.group(1).lower() if type_match else None,
        condition=condition_match.group(1).lower() if condition_match else None,
        engine_status=engine_match.group(1).lower() if engine_match else None,
    )


def assess(text: str) -> HumanitarianAssessment:
    """Build a HumanitarianAssessment from raw report text. Never raises --
    an extraction failure on any one field degrades that field to its
    default, it never blocks the rest of the assessment."""
    text = text or ""
    distress = is_direct_distress_call(text)
    resolved = is_resolved_distress(text)
    case_type = _case_type(text, distress=distress, resolved=resolved)

    rule_ids: list[str] = []
    confidence_basis: list[str] = []
    caveats: list[str] = []

    if distress:
        rule_ids.append("direct_distress_call")
        confidence_basis.append("direct_distress_call")
    if resolved:
        rule_ids.append("resolved_outcome_phrase")
        confidence_basis.append("resolved_outcome_phrase")
    rule_ids.append(f"case_type:{case_type}")

    if resolved:
        lifecycle_value = IncidentLifecycle.RESOLVED.value
    elif distress or is_ongoing_incident(text):
        lifecycle_value = IncidentLifecycle.ACTIVE.value
    else:
        lifecycle_value = IncidentLifecycle.NEEDS_REVIEW.value
    rule_ids.append(f"lifecycle:{lifecycle_value}")

    people = _extract_people(text)
    people_dict = asdict(people)
    matched_roles = [role for role, value in people_dict.items() if value is not None]
    for role in matched_roles:
        rule_ids.append(f"people:{role}")
        confidence_basis.append(f"people_count:{role}={people_dict[role]}")
    if matched_roles and _APPROX_MARKER_RE.search(text):
        # v0: one global caveat, not tied to which specific role the "~"
        # modified -- resolving that precisely needs per-match proximity
        # analysis, a follow-up refinement, not a v0 blocker.
        caveats.append("approximate_count_marker_present")

    vessel = _extract_vessel(text)

    is_operational = case_type not in {
        HumanitarianCaseType.ADVOCACY.value,
        HumanitarianCaseType.UNKNOWN_HUMANITARIAN.value,
    }
    if case_type == HumanitarianCaseType.UNKNOWN_HUMANITARIAN.value:
        publication_recommendation = "review"
        caveats.append("unclassified_case_type")
    elif not is_operational:
        publication_recommendation = "review"
    else:
        publication_recommendation = "publish"

    confidence = 0.4
    if distress:
        confidence += 0.25
    if resolved:
        confidence += 0.15
    confidence += 0.05 * len(matched_roles)
    confidence = min(1.0, round(confidence, 2))

    return HumanitarianAssessment(
        case_type=case_type,
        lifecycle=lifecycle_value,
        is_operational=is_operational,
        publication_recommendation=publication_recommendation,
        confidence=confidence,
        confidence_basis=confidence_basis,
        rule_ids=rule_ids,
        caveats=caveats,
        people=people,
        vessel=vessel,
    )
