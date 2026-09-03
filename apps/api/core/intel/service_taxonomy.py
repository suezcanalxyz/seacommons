# SPDX-License-Identifier: AGPL-3.0-or-later
"""Explicit service/lane classification (docs/fixes.md Task 0.1, section 3.1).

The product surface an event belongs to (``service``) and its workflow
within that surface (``lane``) must be a positive decision, never a
fallback/complement of something else -- the same principle
``core.intel.public_policy.compartment_for_domain`` already applies to the
humanitarian/security split (docs/fixes.md F-07). This module extends that
principle to the finer-grained service/lane model, and in particular gives
Maritime Safety (``not_under_command``, ``aground``,
``restricted_manoeuvrability``) a compartment of its own -- today it has
none, so a self-reported navigational status can currently only land in
"security" (grey_zone) or nowhere.

Target vocabulary (docs/fixes.md 3.1):

    service=humanitarian
      lane=distress | missing | interception | pushback | resolution | land_humanitarian
    service=maritime
      lane=safety | intelligence | environmental

v0 scope: this classifies today's events using the fields the codebase
already produces (``maritime_domain``, ``ais_nav_status_kind``, ``case_type``,
``is_distress``), plus an explicit ``service``/``lane`` pair on the event's
own metadata when a producer has already set one (forward-compatible with
Task 0.2 and later, which start writing those fields directly). It does
NOT yet model ``hypothesis_type`` / the InvestigationHypothesis lifecycle
(docs/fixes.md Phase 1/3) -- that entity does not exist in this codebase
yet, so every Maritime Intelligence classification is ``publishable=False``
here regardless of domain, matching the current, honest state: nothing has
been through the (unbuilt) evidence-gated review workflow yet.

An event this function does not recognise returns
``service=None, lane=None, publishable=False`` -- fail closed, never a
guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

HUMANITARIAN_LANES = frozenset(
    {"distress", "missing", "interception", "pushback", "resolution", "land_humanitarian"}
)
MARITIME_SAFETY_LANE = "safety"
MARITIME_INTELLIGENCE_LANE = "intelligence"
MARITIME_ENVIRONMENTAL_LANE = "environmental"
MARITIME_LANES = frozenset({MARITIME_SAFETY_LANE, MARITIME_INTELLIGENCE_LANE, MARITIME_ENVIRONMENTAL_LANE})

# A navigational-status self-report. Maritime Safety, always -- never a
# Maritime Intelligence hypothesis, never cargo Drift eligible (docs/fixes.md
# global constraint: "not_under_command belongs to service=maritime,
# lane=safety; it is not a Maritime Intelligence hypothesis and is not cargo
# Drift eligible"). "disabled"/"adrift" are the same observation under other
# names used elsewhere in the codebase (core.intel.fusion._GROUNDING_SUBTYPES).
SAFETY_AIS_STATUS_KINDS = frozenset(
    {"not_under_command", "aground", "restricted_manoeuvrability", "disabled", "adrift"}
)

# maritime_domain values that describe a Maritime Intelligence-shaped
# compartment under the pre-taxonomy scheme (core.domain.live_contracts.MaritimeDomain).
_INTELLIGENCE_DOMAINS = frozenset({"grey_zone", "sanctions", "iuu_fishing", "smuggling"})

_HUMANITARIAN_CASE_TYPE_LANES = {
    "distress_sar": "distress",
    "missing_persons": "missing",
    "pushback": "pushback",
    "interception": "interception",
    "shipwreck": "distress",
}


@dataclass(frozen=True)
class ServiceClassification:
    service: str | None
    lane: str | None
    publishable: bool
    reason: str


def _as_metadata(event_or_metadata: Any) -> tuple[Mapping[str, Any], bool]:
    """Accept an IntelEvent (duck-typed via .metadata/.is distress-ish attrs)
    or a plain metadata mapping -- tests and any caller with only the dict."""
    if hasattr(event_or_metadata, "metadata"):
        metadata = event_or_metadata.metadata or {}
    else:
        metadata = event_or_metadata or {}
    return metadata, bool(metadata.get("is_distress"))


def classify_service(event_or_metadata: Any) -> ServiceClassification:
    """Classify one intel event's product-facing service/lane. Fail-closed."""
    metadata, is_distress = _as_metadata(event_or_metadata)

    explicit_service = metadata.get("service")
    explicit_lane = metadata.get("lane")
    if explicit_service == "humanitarian" and explicit_lane in HUMANITARIAN_LANES:
        return ServiceClassification("humanitarian", explicit_lane, True, "explicit")
    if explicit_service == "maritime" and explicit_lane in MARITIME_LANES:
        publishable = explicit_lane != MARITIME_INTELLIGENCE_LANE
        return ServiceClassification("maritime", explicit_lane, publishable, "explicit")

    ais_kind = str(metadata.get("ais_nav_status_kind") or "").strip().lower()
    maritime_domain = str(metadata.get("maritime_domain") or "").strip().lower()
    case_type = str(metadata.get("case_type") or "").strip().lower()

    # Maritime Safety wins over any stale maritime_domain tag still present
    # on the event during migration -- this is precisely the M-04 defect.
    if ais_kind in SAFETY_AIS_STATUS_KINDS:
        return ServiceClassification("maritime", MARITIME_SAFETY_LANE, True, "ais_safety_status")

    if is_distress and not ais_kind:
        lane = _HUMANITARIAN_CASE_TYPE_LANES.get(case_type, "distress")
        return ServiceClassification("humanitarian", lane, True, "humanitarian_distress")

    if maritime_domain in _INTELLIGENCE_DOMAINS:
        # Not yet publishable: no InvestigationHypothesis/evidence-gate exists
        # in this codebase (docs/fixes.md Phase 1/3) for anything to have
        # passed review through.
        return ServiceClassification("maritime", MARITIME_INTELLIGENCE_LANE, False, "intelligence_unreviewed")

    if maritime_domain == "environmental":
        return ServiceClassification("maritime", MARITIME_ENVIRONMENTAL_LANE, False, "environmental_unassessed")

    return ServiceClassification(None, None, False, "unclassified")
