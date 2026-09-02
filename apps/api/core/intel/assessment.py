# SPDX-License-Identifier: AGPL-3.0-or-later
"""Case-specific event assessments (docs/prompt.md PHASE 1, audit IN-1..IN-4).

`ConePanel` renders `descriptionOf(props.type)` -- a fixed sentence per
*category*. Two `not_under_command` events twelve hours and four reports
apart read identically. `descriptionOf` stays as the category explainer;
this module produces the per-*case* assessment: what was actually measured
(with the numbers), what it means (evidence-referenced and caveated), how
strong the evidence is, and what it is explicitly NOT.

Every `assess_*` is a small pure function over structured facts. Nothing here
reads `event.type` to generate prose -- the interpretation is built from the
evidence attached to that one event, so two events of the same type with
different evidence produce different interpretations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

CLASSIFICATION_VERSION = "assessment/v1"

EvidenceLevel = Literal[
    "single_observation", "sustained_observation", "multi_source", "corroborated"
]


@dataclass(frozen=True)
class EventAssessment:
    observation: str
    interpretation: str
    evidence_level: EvidenceLevel
    confidence: float
    confidence_components: dict[str, float] = field(default_factory=dict)
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    recommended_action: Optional[str] = None
    rule_ids: list[str] = field(default_factory=list)
    classification_version: str = CLASSIFICATION_VERSION

    def as_metadata(self) -> dict[str, Any]:
        return {
            "event_assessment": {
                "observation": self.observation,
                "interpretation": self.interpretation,
                "evidence_level": self.evidence_level,
                "confidence": round(self.confidence, 3),
                "confidence_components": {
                    k: round(v, 3) for k, v in self.confidence_components.items()
                },
                "supporting_evidence": self.supporting_evidence,
                "contradicting_evidence": self.contradicting_evidence,
                "caveats": self.caveats,
                "recommended_action": self.recommended_action,
                "rule_ids": self.rule_ids,
                "classification_version": self.classification_version,
            }
        }


def _minutes(seconds: float | None) -> str:
    if not seconds:
        return "an unknown period"
    m = seconds / 60.0
    return f"{m:.0f} minute{'s' if m >= 1.5 else ''}" if m >= 1 else f"{seconds:.0f} seconds"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _combine(components: dict[str, float]) -> float:
    return _clamp(sum(components.values()) / len(components)) if components else 0.0


# ── AIS navigational status ─────────────────────────────────────────────────
def assess_not_under_command(
    *,
    reports: int,
    span_s: float,
    speed_kn: float,
    vessel_type: str | None = None,
    gnss_jamming: bool = False,
) -> EventAssessment:
    sustained = reports >= 3 and span_s >= 600
    observation = (
        f"AIS navigation status 2 (not under command) persisted across {reports} "
        f"report{'s' if reports != 1 else ''} over {_minutes(span_s)}, "
        f"speed {speed_kn:.1f} kn."
    )
    interpretation = (
        "The vessel is reporting itself as not under command, meaning it may be "
        "unable to manoeuvre as required. This is an AIS-transponder observation, "
        "not confirmation of mechanical failure."
    )
    caveats = [
        "AIS navigation status is reported by the vessel; the operational cause "
        "is not independently confirmed.",
    ]
    supporting = [f"sustained: {reports} reports over {_minutes(span_s)}"] if sustained else []
    contradicting = (
        [] if sustained else [f"only {reports} report(s) over {_minutes(span_s)} — below the sustained threshold"]
    )
    components = {
        "persistence": 0.8 if sustained else 0.25,
        "source_reliability": 0.6,  # a transponder self-report
        "rule_strength": 0.5,
    }
    evidence_level: EvidenceLevel = "sustained_observation" if sustained else "single_observation"
    if gnss_jamming:
        interpretation += (
            " The position also overlaps a current GNSS interference area, which "
            "increases the operational relevance of the navigation-status report "
            "but does not prove causation."
        )
        supporting.append("position overlaps an active GNSS interference area")
        components["independent_corroboration"] = 0.6
        evidence_level = "multi_source"
        caveats.append(
            "GNSS interference is contextual; it does not on its own make this a "
            "security event."
        )
    if speed_kn > 0.5:
        contradicting.append(f"still making way at {speed_kn:.1f} kn")
    return EventAssessment(
        observation=observation,
        interpretation=interpretation,
        evidence_level=evidence_level,
        confidence=_combine(components),
        confidence_components=components,
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        caveats=caveats,
        recommended_action="Monitor as vessel safety context." if sustained else "Await further reports.",
        rule_ids=["ais_nav_status:2"],
    )


def assess_sudden_stop(
    *,
    prev_speed_kn: float,
    cur_speed_kn: float,
    samples: int,
    persistence_s: float,
    in_port_zone: bool = False,
    in_anchorage: bool = False,
    nav_status: int | None = None,
    track_displacement_m: float | None = None,
) -> EventAssessment:
    sustained = samples >= 4 and persistence_s >= 600
    observation = (
        f"Speed changed from {prev_speed_kn:.1f} kn to {cur_speed_kn:.1f} kn"
        + (f" and held for {_minutes(persistence_s)} over {samples} fixes." if sustained
           else f" between {samples} observation(s).")
    )
    interpretation = (
        "An abrupt stop was detected outside the current port exclusion model. "
        "This can indicate an incident, a rendezvous, anchoring, traffic "
        "conditions or ordinary manoeuvring; additional track evidence is required."
    )
    contradicting: list[str] = []
    if in_anchorage or nav_status in (1, 5):
        contradicting.append(
            "position is in a known anchorage / nav status is anchored or moored"
        )
    if in_port_zone:
        contradicting.append("stop occurred inside a port approach zone")
    supporting = (
        [f"held for {_minutes(persistence_s)} over {samples} fixes"] if sustained else []
    )
    if track_displacement_m is not None and track_displacement_m < 50:
        supporting.append(f"track displacement only {track_displacement_m:.0f} m since the stop")
    components = {
        "rule_strength": 0.6 if sustained else 0.3,
        "persistence": 0.75 if sustained else 0.2,
        "contradicting_evidence": 0.2 if contradicting else 0.7,
    }
    return EventAssessment(
        observation=observation,
        interpretation=interpretation,
        evidence_level="sustained_observation" if sustained else "single_observation",
        confidence=_combine(components),
        confidence_components=components,
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        caveats=["A speed transition alone is a cue, not a confirmed incident."],
        recommended_action="Review the track for a rendezvous or a casualty." if sustained
        else "Treat as a low-confidence cue pending more fixes.",
        rule_ids=["ais_spike:sudden_stop"],
    )


def assess_rescue_cluster(
    *,
    vessels: int,
    min_distance_nm: float,
    ngo_or_cg_present: bool,
    positions_max_age_s: float,
    converging: bool = False,
    closing_rate_kn: float | None = None,
    active_distress_within_nm: float | None = None,
) -> EventAssessment:
    fresh = positions_max_age_s <= 1800
    observation = (
        f"{vessels} vessels within {min_distance_nm:.1f} nm; "
        f"nearest positions {'fresh' if fresh else f'{positions_max_age_s / 60:.0f} min old'}; "
        + ("at least one is an NGO/coast-guard unit; " if ngo_or_cg_present else "no NGO/CG unit; ")
        + (f"decreasing distance (closing {closing_rate_kn:.1f} kn); " if converging and closing_rate_kn
           else "no measured convergence; ")
        + (f"active distress {active_distress_within_nm:.0f} nm away." if active_distress_within_nm is not None
           else "no active distress nearby.")
    )
    strong = fresh and converging and ngo_or_cg_present
    interpretation = (
        "Multiple vessels are close together and converging near an active "
        "distress — consistent with a rescue in progress."
        if strong and active_distress_within_nm is not None
        else "Multiple vessels are close together. Proximity alone is not "
        "evidence of a coordinated rescue; convergence and freshness are needed."
    )
    supporting: list[str] = []
    contradicting: list[str] = []
    (supporting if fresh else contradicting).append(
        "positions are fresh" if fresh else f"positions up to {positions_max_age_s / 60:.0f} min old"
    )
    (supporting if converging else contradicting).append(
        "vessels are converging" if converging else "no convergence measured (proximity only)"
    )
    components = {
        "freshness": 0.9 if fresh else 0.2,
        "convergence": 0.9 if converging else 0.2,
        "rule_strength": 0.7 if strong else 0.35,
        "context_support": 0.8 if active_distress_within_nm is not None else 0.4,
    }
    return EventAssessment(
        observation=observation,
        interpretation=interpretation,
        evidence_level="corroborated" if (strong and active_distress_within_nm is not None)
        else "multi_source" if strong else "single_observation",
        confidence=_combine(components),
        confidence_components=components,
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        caveats=["Proximity is never called a rescue without measured convergence."],
        recommended_action="Treat as a probable rescue and cross-reference the distress."
        if strong else "Downgrade to a possible cluster pending convergence evidence.",
        rule_ids=["ais_spike:rescue_cluster"],
    )


def assess_ais_gap(
    *,
    silence_s: float,
    last_speed_kn: float,
    in_dark_zone: bool = False,
    nearby_vessels_before: int | None = None,
    nearby_vessels_after: int | None = None,
    local_reporting_ratio: float | None = None,
) -> EventAssessment:
    coverage_collapsed = (
        nearby_vessels_before is not None
        and nearby_vessels_after is not None
        and nearby_vessels_before >= 3
        and nearby_vessels_after == 0
    ) or (local_reporting_ratio is not None and local_reporting_ratio < 0.1)
    observation = (
        f"No AIS position for {_minutes(silence_s)}; last speed {last_speed_kn:.1f} kn"
        + (f"; nearby vessels reporting {nearby_vessels_before}->{nearby_vessels_after}"
           if nearby_vessels_before is not None and nearby_vessels_after is not None else "")
        + (f"; local reporting ratio {local_reporting_ratio:.0%}" if local_reporting_ratio is not None else "")
        + "."
    )
    if coverage_collapsed:
        interpretation = (
            "Nearby AIS traffic disappeared at the same time, so this is most "
            "likely a reception/coverage outage, not a vessel-specific gap. It "
            "must not be described as intentional dark activity."
        )
        evidence_level: EvidenceLevel = "multi_source"
        components = {"coverage_quality": 0.15, "rule_strength": 0.6, "independent_corroboration": 0.8}
        rec = "Classify as a coverage/source outage; do not escalate per vessel."
        contradicting = ["surrounding coverage collapsed simultaneously"]
        supporting: list[str] = []
    else:
        interpretation = (
            "The vessel stopped transmitting while nearby traffic kept reporting, "
            "so local coverage looks healthy and the gap is vessel-specific. This "
            "is an integrity observation, not proof of intent."
        )
        evidence_level = "multi_source" if nearby_vessels_after else "single_observation"
        components = {
            "coverage_quality": 0.8 if (local_reporting_ratio or 0) >= 0.6 else 0.5,
            "rule_strength": 0.6,
            "observation_freshness": 0.6,
        }
        rec = "Flag as a vessel AIS gap; monitor for reacquisition."
        supporting = ["surrounding coverage remained healthy"] if nearby_vessels_after else []
        contradicting = ["known low-coverage area" ] if in_dark_zone else []
    return EventAssessment(
        observation=observation,
        interpretation=interpretation,
        evidence_level=evidence_level,
        confidence=_combine(components),
        confidence_components=components,
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        caveats=["A reception outage is never described as intentional dark activity."],
        recommended_action=rec,
        rule_ids=["ais_anomaly:gap"],
    )


def assess_humanitarian(
    *,
    case_type: str,
    people: dict[str, Any] | None = None,
    vessel: dict[str, Any] | None = None,
    needs: list[str] | None = None,
    lifecycle: str | None = None,
    retrospective: bool = False,
) -> EventAssessment:
    people = people or {}
    vessel = vessel or {}
    needs = needs or []
    counts = ", ".join(
        f"{v} {k}" for k, v in people.items() if isinstance(v, (int, float)) and k != "approximate"
    )
    conditions = ", ".join(k for k, v in vessel.items() if v is True)
    observation = (
        f"Case type {case_type}"
        + (f"; reported people: {counts}" if counts else "")
        + (f"; vessel: {conditions}" if conditions else "")
        + (f"; stated needs: {', '.join(needs)}" if needs else "")
        + (f"; lifecycle {lifecycle}" if lifecycle else "")
        + "."
    )
    if retrospective:
        interpretation = (
            f"This post references a past event ({case_type}) rather than an "
            "active incident. It should not open or reopen an operational case."
        )
        rec = "Record as a retrospective reference; no operational action."
        evidence_level: EvidenceLevel = "single_observation"
    elif case_type in {"advocacy", "humanitarian_update"}:
        interpretation = (
            "This is a non-originating humanitarian communication. It carries no "
            "new position or operational fact on its own."
        )
        rec = "Attach to the timeline; do not raise a new marker."
        evidence_level = "single_observation"
    else:
        interpretation = (
            f"A {case_type.replace('_', ' ')} is reported by a humanitarian source. "
            "The source's reliability does not by itself verify the coordinate or "
            "the counts; treat extracted values as claims pending corroboration."
        )
        rec = "Verify position and counts against any second source."
        evidence_level = "single_observation"
    components = {
        "source_reliability": 0.7,
        "rule_strength": 0.5,
        "independent_corroboration": 0.2,
    }
    return EventAssessment(
        observation=observation,
        interpretation=interpretation,
        evidence_level=evidence_level,
        confidence=_combine(components),
        confidence_components=components,
        supporting_evidence=[c for c in (counts, conditions) if c],
        contradicting_evidence=[],
        caveats=[
            "Source credibility is not location credibility; an extracted "
            "coordinate is not a verified coordinate.",
        ],
        recommended_action=rec,
        rule_ids=[f"humanitarian:{case_type}"],
    )


_DISPATCH = {
    "not_under_command": assess_not_under_command,
    "sudden_stop": assess_sudden_stop,
    "rescue_cluster": assess_rescue_cluster,
    "ais_gap": assess_ais_gap,
    "gap": assess_ais_gap,
    "humanitarian": assess_humanitarian,
}


def assess(kind: str, facts: dict[str, Any]) -> Optional[EventAssessment]:
    """Dispatch to the right `assess_*` by a coarse kind string, or None."""
    fn = _DISPATCH.get(kind)
    if fn is None:
        return None
    try:
        return fn(**facts)
    except TypeError:
        return None
