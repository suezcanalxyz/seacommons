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

``needs``, ``actors``, ``location_claims``, ``temporal_claims`` and
``resolution_evidence`` are deterministic, regex/registry-based extractions
-- like every other field here, a controlled-vocabulary or raw-span match,
never free-text generation. ``lifecycle`` here is the TEXT-STATED outcome
only (active/resolved/needs_review); the fourth value, ``archived``, is a
time-based transition this module cannot see from text alone and stays
exactly where it already lives, ``core.intel.lifecycle``.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from core.domain.live_contracts import HumanitarianCaseType, IncidentLifecycle
from core.intel.geoextract import (
    _PLACES_SORTED,
    _RELATIVE_DIRECTION,
    _RELATIVE_DISTANCE,
    _RESOLVED_DISTRESS_PATTERNS,
    is_direct_distress_call,
    is_ongoing_incident,
    is_resolved_distress,
)
from core.intel.humanitarian import _case_type
from core.intel.ngo_registry import NGO_VESSELS, UNCONFIRMED_MMSI

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

_NEED_PATTERNS: dict[str, re.Pattern[str]] = {
    "rescue": re.compile(
        r"\b(?:urgent\s+)?rescue\s+(?:is\s+)?(?:urgently\s+)?needed\b"
        r"|\bneeds?\s+(?:urgent\s+)?rescue\b|\brescue\s+is\s+urgent\b",
        re.I,
    ),
    "medical_assistance": re.compile(
        r"\bmedical\s+(?:assistance|attention|emergency|evacuation)\b|\bmedevac\b", re.I,
    ),
    "water": re.compile(r"\b(?:out\s+of|no|needs?)\s+water\b", re.I),
    "food": re.compile(r"\b(?:out\s+of|no|needs?)\s+food\b", re.I),
    "fuel": re.compile(r"\b(?:out\s+of|no|needs?)\s+fuel\b", re.I),
}

# Generic responder/authority mentions -- distinct from the specific named
# NGO/coastguard vessels below (a vessel NAME is direct evidence a specific
# asset was mentioned; these are evidence an authority TYPE was mentioned,
# even with no specific vessel named).
_AUTHORITY_ACTOR_PATTERNS: dict[str, re.Pattern[str]] = {
    "libyan_coast_guard": re.compile(r"\blibyan\s+coast\s*guard\b", re.I),
    "italian_coast_guard": re.compile(r"\bitalian\s+coast\s*guard\b|\bguardia\s+costiera\b", re.I),
    "tunisian_coast_guard": re.compile(r"\btunisian\s+coast\s*guard\b", re.I),
    "greek_coast_guard": re.compile(r"\bgreek\s+coast\s*guard\b", re.I),
    "maltese_authorities": re.compile(r"\bmaltese\s+(?:coast\s*guard|authorities|armed\s+forces)\b", re.I),
    "mrcc": re.compile(r"\bmrcc\b", re.I),
    "frontex": re.compile(r"\bfrontex\b", re.I),
}

# Known SAR NGO / coastguard vessel names (core.intel.ngo_registry), longest
# first so e.g. "Sea Watch 5" is matched whole rather than partially by a
# shorter unrelated prefix.
_KNOWN_VESSEL_NAMES = sorted(
    {
        str(info["name"]) for info in NGO_VESSELS.values() if info.get("name")
    }
    | set(UNCONFIRMED_MMSI.keys()),
    key=len,
    reverse=True,
)

_TEMPORAL_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bsince\s+(?:yesterday(?:\s+evening|\s+morning|\s+night)?|last\s+night"
        r"|this\s+morning|this\s+afternoon|this\s+evening)\b",
        r"\b\d{1,3}\s*(?:hours?|hrs?|days?)\s+ago\b",
        r"\bno\s+contact\s+for\s+\d{1,3}\s*(?:hours?|hrs?|days?)\b",
        r"\bovernight\b",
        r"\blast\s+night\b",
    )
)

# A relative distance+direction claim, e.g. "90nm south of Lampedusa" --
# reuses the exact same fragments extract_relative_coords() already relies
# on for real coordinate derivation, so this claim text and that pipeline's
# geometry can never silently disagree on what counts as a distance/
# direction phrase.
_RELATIVE_LOCATION_RE = re.compile(
    _RELATIVE_DISTANCE + r"\s+" + _RELATIVE_DIRECTION + r"\s+(?:of|from)\s+(?:the\s+)?[\w\séèàïô'-]{2,30}",
    re.I,
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


def _extract_needs(text: str) -> list[str]:
    return [need for need, pattern in _NEED_PATTERNS.items() if pattern.search(text)]


def _extract_actors(text: str) -> list[str]:
    actors: list[str] = []
    for name in _KNOWN_VESSEL_NAMES:
        if re.search(r"\b" + re.escape(name) + r"\b", text, re.I):
            actors.append(name)
    for actor, pattern in _AUTHORITY_ACTOR_PATTERNS.items():
        if pattern.search(text):
            actors.append(actor)
    return actors


def _extract_location_claims(text: str) -> list[str]:
    claims: list[str] = []
    for match in _RELATIVE_LOCATION_RE.finditer(text):
        claims.append(re.sub(r"\s+", " ", match.group(0)).strip())
    seen_places: set[str] = set()
    for place, _coords in _PLACES_SORTED:
        if place in seen_places:
            continue
        if re.search(r"\b" + re.escape(place).replace(r"\ ", r"\s+") + r"\b", text, re.I):
            claims.append(place)
            seen_places.add(place)
    return claims


def _extract_temporal_claims(text: str) -> list[str]:
    claims: list[str] = []
    for pattern in _TEMPORAL_PATTERNS:
        for match in pattern.finditer(text):
            span = re.sub(r"\s+", " ", match.group(0)).strip().lower()
            if span not in claims:
                claims.append(span)
    return claims


def _extract_resolution_evidence(text: str, *, resolved: bool) -> list[str]:
    if not resolved:
        return []
    evidence: list[str] = []
    for pattern in _RESOLVED_DISTRESS_PATTERNS:
        match = pattern.search(text)
        if match:
            evidence.append(re.sub(r"\s+", " ", match.group(0)).strip())
    return evidence


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
    needs = _extract_needs(text)
    actors = _extract_actors(text)
    location_claims = _extract_location_claims(text)
    temporal_claims = _extract_temporal_claims(text)
    resolution_evidence = _extract_resolution_evidence(text, resolved=resolved)

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
        needs=needs,
        actors=actors,
        location_claims=location_claims,
        temporal_claims=temporal_claims,
        resolution_evidence=resolution_evidence,
    )
