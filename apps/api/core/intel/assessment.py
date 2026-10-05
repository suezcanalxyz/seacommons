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

from core.domain.visual_category import classify_visual_category

CLASSIFICATION_VERSION = "assessment-v1"


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


def _category_assessment(
    category: str,
    metadata: dict[str, Any],
    *,
    event_type: str = "",
    source: str = "",
    linked_mmsi: str = "",
) -> EventAssessment | None:
    """Evidence-aware assessment for each public semantic Live category."""
    detection = str(
        metadata.get("detection_reason")
        or metadata.get("detail")
        or metadata.get("public_summary")
        or ""
    ).strip()
    reasons = [str(v) for v in (metadata.get("reason_codes") or ()) if v]
    groups = [str(v) for v in (metadata.get("independence_groups") or ()) if v]
    independent = int(metadata.get("independent_source_count") or len(groups) or 1)
    corroborated = independent >= 2 or bool(metadata.get("corroborated"))
    evidence_level = str(metadata.get("evidence_stage") or metadata.get("analysis_state") or "observed")
    evidence_level = {
        "observation": "observed",
        "evidence_candidate": "derived",
        "evidence": "derived",
    }.get(evidence_level, evidence_level)

    def assessment(
        observation: str,
        interpretation: str,
        *,
        confidence: float,
        caveat: str,
        basis: list[str],
        action: str = "operator_review",
    ) -> EventAssessment:
        return EventAssessment(
            observation=observation,
            interpretation=interpretation,
            evidence_level="corroborated" if corroborated else evidence_level,
            confidence=confidence,
            confidence_basis=basis,
            supporting_evidence=[observation],
            caveats=[caveat],
            recommended_action=action,
            rule_ids=reasons[:8],
        )

    mmsi = str(linked_mmsi or metadata.get("linked_mmsi") or metadata.get("mmsi") or "").strip()
    movement = metadata.get("movement_evidence") if isinstance(metadata.get("movement_evidence"), dict) else {}

    if category == "spoofing":
        distance_km = movement.get("distance_km")
        implied_kn = movement.get("implied_speed_kn")
        delta_s = movement.get("time_delta_s")
        pieces = []
        if distance_km is not None:
            pieces.append(f"{float(distance_km):.1f} km relocation")
        if delta_s is not None:
            pieces.append(f"over {float(delta_s) / 60:.1f} min")
        if implied_kn is not None:
            pieces.append(f"implied speed {float(implied_kn):.0f} kn")
        observation = detection or (
            f"AIS position-integrity cue for {mmsi or 'this vessel'}"
            + (f": {', '.join(pieces)}." if pieces else ".")
        )
        interpretation = (
            (f"Detector evidence: {detection}. " if detection else "")
            + "The observed AIS positions are not physically consistent with ordinary vessel movement"
        )
        if pieces:
            interpretation += f" ({'; '.join(pieces)})"
        interpretation += (
            ". This can reflect spoofing, transponder or GNSS error, data interleaving, "
            "or an upstream reception problem. "
        )
        interpretation += (
            "Independent evidence is present, so the anomaly is stronger than a single AIS cue."
            if corroborated
            else "No independent lineage currently confirms deliberate spoofing."
        )
        return assessment(observation, interpretation, confidence=0.8 if corroborated else 0.62,
                          caveat="Impossible movement is evidence of position inconsistency, not proof of intent or spoofing.",
                          basis=["ais_position_sequence", *(["independent_lineage"] if corroborated else [])],
                          action="inspect_trigger_track")

    if category == "ais_gap":
        evidence = metadata.get("anomaly_evidence") if isinstance(metadata.get("anomaly_evidence"), dict) else {}
        duration = evidence.get("silent_seconds")
        observation = detection or (
            f"AIS reporting gap for {mmsi or 'this vessel'}"
            + (f" lasting {float(duration) / 60:.0f} min." if duration else ".")
        )
        coverage = str(metadata.get("anomaly_type") or "") == "coverage_gap"
        interpretation = (
            "Nearby traffic shows the same reception loss, so this gap is better explained by coverage or source availability than by vessel-specific behaviour."
            if coverage
            else "This vessel stopped reporting while surrounding reception remained comparatively available. The gap is operationally relevant, but AIS silence alone cannot establish deliberate dark activity."
        )
        return assessment(observation, interpretation, confidence=0.48 if coverage else 0.68,
                          caveat="AIS silence can result from equipment, reception, source coverage, or deliberate shutdown.",
                          basis=["ais_reporting_continuity", "local_coverage_context"])

    if category == "rendezvous":
        partner = metadata.get("other_mmsi") or metadata.get("partner_mmsi")
        distance = metadata.get("min_distance_nm") or metadata.get("distance_nm")
        dwell = metadata.get("duration_minutes") or metadata.get("dwell_minutes")
        observation = detection or (
            f"Close vessel interaction involving {mmsi or 'this vessel'}"
            + (f" and {partner}" if partner else "")
            + (f"; minimum separation {float(distance):.2f} nm" if distance is not None else "")
            + (f" for about {float(dwell):.0f} min" if dwell is not None else "")
            + "."
        )
        return assessment(
            observation,
            "The tracks show sustained close-proximity behaviour consistent with a rendezvous or ship-to-ship interaction. The geometry does not by itself reveal cargo transfer, coordination purpose, or illegality.",
            confidence=0.72 if corroborated else 0.58,
            caveat="Proximity is behavioural evidence, not proof of transfer or intent.",
            basis=["multi_vessel_ais_geometry"],
        )

    if category == "loitering":
        duration = metadata.get("duration_minutes") or metadata.get("dwell_minutes")
        observation = detection or (
            "Low-mobility or repeated-area dwell detected"
            + (f" for about {float(duration):.0f} min." if duration is not None else ".")
        )
        return assessment(
            observation,
            "The vessel remained in a constrained area longer than expected for a simple transit. Anchoring, waiting orders, fishing, weather, traffic and normal work remain plausible explanations.",
            confidence=0.52,
            caveat="Loitering is contextual behaviour and is not inherently suspicious.",
            basis=["ais_dwell_pattern"],
        )

    if category == "infrastructure":
        infra = metadata.get("infrastructure") if isinstance(metadata.get("infrastructure"), dict) else {}
        name = infra.get("name") or infra.get("kind") or "mapped maritime infrastructure"
        distance = infra.get("distance_km")
        observation = detection or (
            f"Sustained vessel activity near {name}"
            + (f" at approximately {float(distance):.1f} km." if distance is not None else ".")
        )
        return assessment(
            observation,
            "The track places the vessel close to mapped infrastructure for long enough to merit contextual review. Proximity alone does not establish interference, surveillance, sabotage, or hostile intent.",
            confidence=0.55,
            caveat="Interpret proximity with vessel role, traffic lanes and lawful operations.",
            basis=["ais_track", "infrastructure_geofence"],
        )

    if category == "sanctions":
        port_call = metadata.get("port_call") if isinstance(metadata.get("port_call"), dict) else {}
        port = port_call.get("port")
        observation = detection or (
            "A vessel identifier matches sanctions context"
            + (f" during an observed port stay at {port}." if port else ".")
        )
        interpretation = (
            "A strong vessel identifier links this track to a sanctions-listed identity"
            + (f", with an observed port stay at {port}" if port else "")
            + ". This is relevant for compliance review, but SeaCommons does not infer sanctions evasion or a legal violation from identity and movement alone."
        )
        return assessment(observation, interpretation, confidence=0.82 if metadata.get("sanctions_matched") else 0.62,
                          caveat="Legal applicability depends on jurisdiction, listing scope, ownership and transaction context.",
                          basis=["vessel_identity_match", *(["port_call_observation"] if port else [])])

    if category == "identity":
        observation = detection or f"Identity inconsistency detected for {mmsi or 'a vessel record'}."
        return assessment(
            observation,
            "AIS or static identity fields are inconsistent with another observed or reference attribute. Stale registry data, operator entry error, transponder replacement and deliberate identity manipulation remain competing explanations.",
            confidence=0.58,
            caveat="Identity mismatches require registry and historical cross-checks before attribution.",
            basis=["ais_identity_fields"],
        )

    if category == "navigation_casualty":
        observation = detection or "AIS safety or navigation state indicates a possible navigation casualty."
        return assessment(
            observation,
            "The vessel is broadcasting a safety-relevant navigation state or distress identity. This is operationally important, but remains an AIS self-report until corroborated by movement, radio, authority, or another independent source.",
            confidence=0.7 if corroborated else 0.55,
            caveat="AIS safety states can be stale or manually mis-set.",
            basis=["ais_safety_state"],
        )

    if category in {"humanitarian_alarm_phone", "distress", "iom"}:
        people = metadata.get("people_reported") or metadata.get("persons")
        observation = detection or ("Humanitarian distress report" + (f" involving {people} people." if people is not None else "."))
        return assessment(
            observation,
            "This is a humanitarian case report describing possible danger to people at sea. Source attribution, coordinates, updates and rescue or resolution evidence remain distinct from official confirmation.",
            confidence=0.72 if category == "humanitarian_alarm_phone" else 0.6,
            caveat="Reported facts can change as a case develops; later updates should remain visible.",
            basis=["humanitarian_source_report"],
            action="monitor_case_updates",
        )

    if category in {"civil_sar", "state_sar", "ngo_activity"}:
        observation = detection or "SAR-related vessel activity observed from AIS or public operational data."
        return assessment(
            observation,
            "The vessel's location or movement is relevant to a search-and-rescue context. Presence, approach or proximity can support a response assessment, but does not by itself prove that a rescue occurred or identify the vessel as the casualty.",
            confidence=0.5,
            caveat="SAR-role interpretation requires case linkage and time-aligned movement.",
            basis=["ais_operational_activity"],
        )

    if category == "piracy":
        observation = detection or "Public-source maritime security incident reported."
        return assessment(
            observation,
            "The source describes a piracy, armed-robbery or security event. SeaCommons records the report and its location/time lineage; attribution, actors and legal classification require corroboration.",
            confidence=0.5,
            caveat="Security reports can be preliminary and should be independently cross-checked.",
            basis=["public_security_report"],
        )

    if category == "environmental":
        observation = detection or "Environmental maritime hazard reported or detected."
        return assessment(
            observation,
            "The event indicates a possible pollution or environmental hazard. The current record establishes the observation or report context, not source attribution, extent, or liability.",
            confidence=0.5,
            caveat="Extent and causation require sensor, imagery or authority corroboration.",
            basis=["environmental_observation"],
        )

    if category == "hazard":
        observation = detection or "GDACS hazard context intersects the maritime operating area."
        return assessment(
            observation,
            "This is regional hazard context rather than a vessel incident. It can affect route deviation, distress plausibility, weather exposure or operational constraints, but does not directly identify a maritime casualty.",
            confidence=0.65,
            caveat="Hazard context should not be presented as vessel-specific evidence.",
            basis=["gdacs_public_hazard"],
            action="use_as_context",
        )

    if category in {"news", "social"}:
        observation = detection or "Public-source report retained as contextual evidence."
        return assessment(
            observation,
            "This item contributes public reporting context. It is useful for chronology and corroboration, but publication on a news or social source is not itself sensor confirmation of the reported maritime event.",
            confidence=0.35,
            caveat="Treat public reporting as a separate evidence lineage, not as ground truth.",
            basis=["public_reporting"],
            action="cross_reference",
        )

    if category == "context":
        observation = detection or "Maritime contextual observation retained for situational awareness."
        return assessment(
            observation,
            "This record provides context for nearby maritime activity. It is not currently classified as a stronger incident family and should not be read as an allegation or finding.",
            confidence=0.3,
            caveat="Context records require additional evidence before escalation.",
            basis=["context_observation"],
            action="monitor",
        )
    return None


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

    event_type = str(getattr(event, "type", "") or metadata.get("type") or "")
    source = str(getattr(event, "source", "") or metadata.get("source") or "")
    linked_mmsi = str(getattr(event, "linked_mmsi", "") or metadata.get("linked_mmsi") or metadata.get("mmsi") or "")
    maritime_domain = (
        str(event.maritime_domain())
        if hasattr(event, "maritime_domain") and callable(getattr(event, "maritime_domain"))
        else str(metadata.get("maritime_domain") or "")
    )
    category = classify_visual_category(
        source=source,
        event_type=event_type,
        maritime_domain=maritime_domain,
        humanitarian_case_type=metadata.get("humanitarian_case_type"),
        metadata=metadata,
    )
    return _category_assessment(
        category,
        metadata,
        event_type=event_type,
        source=source,
        linked_mmsi=linked_mmsi,
    )
