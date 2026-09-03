# SPDX-License-Identifier: AGPL-3.0-or-later
"""Case-specific event interpretation (docs/prompt.md Phase 1).

``ConePanel.jsx``'s ``Interpretation = descriptionOf(props.type)`` produces
nearly identical text for every event of the same type -- a category
explanation, not an assessment of what was actually observed. This module
replaces that for the kinds it covers with an ``EventAssessment`` built
from the specific evidence attached to *this* event: two events of the
same ``ais_nav_status_kind`` with different report counts, durations, or
jamming context must produce different ``interpretation`` text, not the
same canned sentence.

``descriptionOf(type)`` (or whatever the frontend calls it) is not removed
by this module -- it stays as the category label. This is the layer above
it: read the evidence, do not invent facts the event doesn't carry.

v0 scope: covers the two Maritime Safety kinds this session already fixed
routing for (``not_under_command``, ``aground``) plus
``restricted_manoeuvrability``, all produced by
``core.intel.vessel_incident_monitor``. Other event families (sudden_stop,
rescue_cluster, AIS gap, ...) are out of scope for this PR -- see
docs/prompt.md Phase 1 for their worked examples when this gets extended.
An event this module has no assessor for returns ``None``: never fall back
to generic prose from ``event.type`` (docs/prompt.md: "Do NOT generate
generic prose from event.type").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CLASSIFICATION_VERSION = "assessment-v0"


@dataclass(frozen=True)
class EventAssessment:
    observation: str
    interpretation: str
    # docs/fixes.md section 3.2 evidence ladder: observed | derived |
    # corroborated | assessed | confirmed.
    evidence_level: str
    confidence: float
    confidence_basis: list[str] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    recommended_action: str = ""
    rule_ids: list[str] = field(default_factory=list)
    classification_version: str = CLASSIFICATION_VERSION


_NAV_STATUS_CAVEAT = (
    "AIS navigation status reported by the vessel; operational cause is not "
    "independently confirmed."
)


def _observation_text(metadata: dict[str, Any], fallback: str) -> str:
    # vessel_incident_monitor.py only sets detection_reason once the
    # sustained-report rule actually fired -- it is already the specific,
    # reproducible evidence string ("Flagged after N report(s) over Ns
    # (rule: >=N reports and >=Ns sustained)."), not boilerplate.
    return str(metadata.get("detection_reason") or fallback)


def _assess_not_under_command(metadata: dict[str, Any]) -> EventAssessment:
    observation = _observation_text(
        metadata, "AIS navigation status 2 (not under command) reported."
    )
    interpretation = (
        "The vessel is reporting itself as not under command, meaning it may "
        "be unable to manoeuvre as required. This is an AIS-transponder "
        "observation, not confirmation of mechanical failure."
    )
    supporting = [observation]
    confidence_basis = ["ais_transponder_self_report", "sustained_report_threshold_met"]
    confidence = 0.5
    if bool(metadata.get("in_jamming_zone")):
        interpretation += (
            " Position also overlaps a current GNSS interference area, "
            "increasing the operational relevance of the navigation-status "
            "report but not proving causation."
        )
        supporting.append("gnss_jamming_zone_overlap")
        confidence_basis.append("gnss_jamming_zone_overlap")
        confidence = 0.6
    return EventAssessment(
        observation=observation,
        interpretation=interpretation,
        evidence_level="observed",
        confidence=confidence,
        confidence_basis=confidence_basis,
        supporting_evidence=supporting,
        caveats=[_NAV_STATUS_CAVEAT],
        recommended_action="operator_review",
        rule_ids=["not_under_command_sustained"],
    )


def _assess_restricted_manoeuvrability(metadata: dict[str, Any]) -> EventAssessment:
    observation = _observation_text(
        metadata, "AIS navigation status 3 (restricted manoeuvrability) reported."
    )
    return EventAssessment(
        observation=observation,
        interpretation=(
            "The vessel is reporting restricted ability to manoeuvre. This status "
            "is also broadcast continuously by dredgers, cable layers and survey "
            "vessels performing routine work; this assessment does not yet check "
            "the vessel's role, so it cannot distinguish routine work from a "
            "genuine casualty."
        ),
        evidence_level="observed",
        confidence=0.3,
        confidence_basis=["ais_transponder_self_report", "sustained_report_threshold_met"],
        supporting_evidence=[observation],
        contradicting_evidence=[],
        caveats=[
            _NAV_STATUS_CAVEAT,
            "No vessel-role check yet: a dredger/cable-layer/survey vessel broadcasts "
            "this continuously as routine work, not distress.",
        ],
        recommended_action="operator_review",
        rule_ids=["restricted_manoeuvrability_sustained"],
    )


def _assess_aground(metadata: dict[str, Any]) -> EventAssessment:
    observation = _observation_text(metadata, "AIS navigation status 6 (aground) reported.")
    return EventAssessment(
        observation=observation,
        interpretation=(
            "The vessel is reporting itself aground via AIS navigation status. "
            "This is an operational grounding report; it is not yet independently "
            "confirmed by an external source (coast guard, NGO, or a corroborating "
            "sensor)."
        ),
        evidence_level="observed",
        confidence=0.7,
        confidence_basis=["ais_transponder_self_report", "sustained_report_threshold_met"],
        supporting_evidence=[observation],
        caveats=[_NAV_STATUS_CAVEAT],
        recommended_action="published_operational_incident",
        rule_ids=["aground_sustained"],
    )


_ASSESSORS = {
    "not_under_command": _assess_not_under_command,
    "restricted_manoeuvrability": _assess_restricted_manoeuvrability,
    "aground": _assess_aground,
}


def build_assessment(event: Any) -> EventAssessment | None:
    """Case-specific assessment for one intel event, or ``None`` if this
    module has no assessor for its kind yet -- never a generic fallback."""
    metadata = getattr(event, "metadata", None)
    if metadata is None and isinstance(event, dict):
        metadata = event
    metadata = metadata or {}
    kind = str(metadata.get("ais_nav_status_kind") or "").strip().lower()
    assessor = _ASSESSORS.get(kind)
    if assessor is None:
        return None
    return assessor(metadata)
