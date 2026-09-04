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


def _assess_sudden_stop(metadata: dict[str, Any]) -> EventAssessment:
    samples = int(metadata.get("stop_samples") or 1)
    persistence_s = float(metadata.get("stop_persistence_s") or 0.0)
    displacement_nm = metadata.get("stop_displacement_nm")
    promoted = str(metadata.get("spike_type") or "") == "sudden_stop"
    observation = (
        f"AIS speed-stop cue held for {persistence_s / 60:.0f} min over {samples} fixes"
        + (
            f" with {float(displacement_nm):.2f} nm displacement."
            if displacement_nm is not None
            else "."
        )
    )
    return EventAssessment(
        observation=observation,
        interpretation=(
            "An abrupt stop persisted outside the detector's port exclusion. "
            "This can indicate an incident, rendezvous, anchoring, traffic conditions, "
            "or ordinary manoeuvring; it is a track-derived cue, not confirmation."
        ),
        evidence_level="derived",
        confidence=0.65 if promoted else 0.35,
        confidence_basis=[
            "ais_track_speed_transition",
            "persistence_threshold_met" if promoted else "single_transition_cue",
        ],
        supporting_evidence=[observation],
        caveats=["A speed transition alone is a cue, not a confirmed incident."],
        recommended_action="operator_review" if promoted else "await_more_fixes",
        rule_ids=["ais_spike:sudden_stop"],
    )


def _assess_rescue_cluster(metadata: dict[str, Any]) -> EventAssessment:
    vessels = int(metadata.get("cluster_size") or 0)
    converging = bool(metadata.get("converging"))
    age_s = float(metadata.get("positions_max_age_s") or 0.0)
    distress = metadata.get("near_active_distress")
    fresh = age_s <= 1800
    strong = converging and fresh and bool(distress)
    observation = (
        f"{vessels} vessels clustered; positions up to {age_s / 60:.0f} min old; "
        f"converging={'yes' if converging else 'no'}; "
        f"active distress nearby={'yes' if distress else 'no'}."
    )
    return EventAssessment(
        observation=observation,
        interpretation=(
            "Fresh vessels are converging near an active distress report, a pattern "
            "consistent with a rescue response but not confirmation of one."
            if strong
            else "Vessel proximity is a coordination cue only; freshness, convergence, "
            "and distress context are insufficient for a rescue conclusion."
        ),
        evidence_level="corroborated" if strong else "derived",
        confidence=0.75 if strong else 0.35,
        confidence_basis=[
            "ais_multi_vessel_geometry",
            *( ["measured_convergence"] if converging else [] ),
            *( ["active_distress_proximity"] if distress else [] ),
        ],
        supporting_evidence=[observation],
        caveats=["Proximity alone is never treated as proof of a rescue."],
        recommended_action="cross_reference_distress" if strong else "monitor_cluster",
        rule_ids=["ais_spike:rescue_cluster"],
    )


def _assess_ais_gap(metadata: dict[str, Any]) -> EventAssessment:
    anomaly_type = str(metadata.get("anomaly_type") or "")
    evidence = metadata.get("anomaly_evidence") or {}
    silence_s = float(evidence.get("silent_seconds") or 0.0)
    before = evidence.get("nearby_vessels_before")
    after = evidence.get("nearby_vessels_after")
    ratio = evidence.get("local_reporting_ratio")
    observation = f"AIS silence lasted {silence_s / 60:.0f} min"
    if before is not None and after is not None:
        observation += f"; nearby reporting {before}->{after}"
    if ratio is not None:
        observation += f"; local reporting ratio {float(ratio):.0%}"
    observation += "."
    coverage = anomaly_type == "coverage_gap"
    return EventAssessment(
        observation=observation,
        interpretation=(
            "Nearby AIS traffic also disappeared, indicating reception or source coverage "
            "loss rather than vessel-specific intent."
            if coverage
            else "The vessel stopped reporting while nearby AIS coverage remained available. "
            "This is a vessel-specific integrity observation, not proof of intent."
        ),
        evidence_level="derived",
        confidence=0.65 if not coverage else 0.45,
        confidence_basis=[
            "ais_silence_duration",
            "local_coverage_comparison",
        ],
        supporting_evidence=[observation],
        caveats=["AIS silence alone does not establish deliberate dark activity."],
        recommended_action="treat_as_coverage_context" if coverage else "operator_review",
        rule_ids=[f"ais_anomaly:{anomaly_type}"],
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
    if assessor is not None:
        return assessor(metadata)

    spike_type = str(metadata.get("spike_type") or "").strip().lower()
    if spike_type in {"possible_sudden_stop", "sudden_stop"}:
        return _assess_sudden_stop(metadata)
    if spike_type in {"possible_rescue_cluster", "rescue_cluster"}:
        return _assess_rescue_cluster(metadata)

    anomaly_type = str(metadata.get("anomaly_type") or "").strip().lower()
    if anomaly_type in {"gap", "coverage_gap"}:
        return _assess_ais_gap(metadata)
    return None
