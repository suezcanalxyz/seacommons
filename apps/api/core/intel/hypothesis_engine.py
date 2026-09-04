# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live wiring for core.intel.hypothesis (docs/fixes.md M14.3).

Real observations/features/episodes creating and updating persisted
InvestigationHypothesis records -- the piece M6's own module explicitly
left for "a separate, later PR" (core.intel.hypothesis's module docstring).

Scope of this PR: four of the six hypothesis types have gate evidence that
is genuinely self-contained within one core.live.episode_builder episode
(dark_transit, covert_rendezvous, position_spoofing, infrastructure_pattern).
The other two -- identity_deception (needs >=2 independent SOURCES, which
a single MDA-derived episode never has) and sanctions_evasion_pattern
(needs an official-list match PLUS independent behavioural evidence, i.e.
genuinely cross-episode/cross-family correlation) -- are deliberately left
unwired here rather than approximated with a heuristic that could
mis-satisfy their gates; see docs/fixes.md M14.3 follow-up.

Exit gate: "a single AIS observation must never create a published
allegation." Structurally guaranteed two ways: this module never calls
core.intel.hypothesis.transition(..., "assessed"/"published") at all --
reaching those states always needs a separate, explicitly human-reviewed
action outside this engine -- and a hypothesis only ever advances past
"candidate" once at least two distinct signal ids corroborate it (the
gate functions below each already independently require 2+ pieces of
evidence, matching core.intel.hypothesis's own docstring guarantee).

"Official sanctions match alone remains an official-list fact, not
sanctions-evasion behaviour": guaranteed by omission -- this module never
maps any family to "sanctions_evasion_pattern" at all, so a sanctions
match can never, by construction, become an evasion-behaviour hypothesis
through this path (core.mda.vessel_subject.sanctions_fact_for, M5.1, is
the correct fact-only projection for a bare match).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from core.intel.hypothesis import (
    InvestigationHypothesis,
    evaluate_gate,
    new_hypothesis,
    transition,
)
from core.intel.hypothesis_store import get_hypothesis, save_hypothesis
from core.intel.store import IntelEvent, intel_store

# Only families whose gate evidence is self-contained within one episode
# are wired -- see module docstring.
_FAMILY_HYPOTHESIS_TYPE: dict[str, str] = {
    "gap_episode": "dark_transit",
    "rendezvous_episode": "covert_rendezvous",
    "spoofing_episode": "position_spoofing",
    "infrastructure_proximity_episode": "infrastructure_pattern",
}

_MIN_EVIDENCE_FOR_COLLECTING = 2


def event_to_episode_input_feature(event: IntelEvent) -> Optional[dict[str, Any]]:
    """The minimal feature shape core.live.vessel_episodes.
    coalesce_security_vessel_episodes() needs for grouping -- built
    directly from the internal IntelEvent, not through
    core.live.projection._public_intel_feature(): that function's
    domain/type eligibility gates decide what is safe to show publicly and
    would silently exclude signal types (e.g. ais_rendezvous) that never
    reach the public-safe subset but are still real internal evidence this
    engine must see.
    """
    mmsi = str(event.linked_mmsi or "").strip()
    if len(mmsi) != 9 or not mmsi.isdigit():
        return None
    coordinates = (
        [event.lon, event.lat] if event.lat is not None and event.lon is not None else []
    )
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": coordinates},
        "properties": {
            "id": event.id,
            "timestamp_utc": event.timestamp_utc,
            "linked_mmsi": mmsi,
            "anomaly_type": event.metadata.get("anomaly_type"),
            "ais_nav_status_kind": event.metadata.get("ais_nav_status_kind"),
            "severity": event.severity,
            "source": event.source,
            "incident_lifecycle": event.metadata.get("incident_lifecycle"),
        },
    }


def _evaluate_gate_for_family(
    hypothesis_type: str, events: list[IntelEvent],
) -> tuple[bool, str]:
    if hypothesis_type == "dark_transit":
        gap_reasons = [
            e.metadata.get("gap_reason") for e in events
            if isinstance(e.metadata.get("gap_reason"), dict)
        ]
        has_isolated = any(gr.get("hypothesis") == "vessel_gap" for gr in gap_reasons)
        confidence = max(
            (float(gr.get("confidence") or 0.0) for gr in gap_reasons), default=0.0,
        )
        return evaluate_gate(
            "dark_transit",
            has_isolated_gap_feature=has_isolated, coverage_confidence=confidence,
        )
    if hypothesis_type == "covert_rendezvous":
        has_rendezvous = any(
            e.metadata.get("anomaly_type") in {"ais_rendezvous", "rendezvous", "sts"}
            for e in events
        )
        irregularities = tuple(
            sorted({"dark_party" for e in events if e.metadata.get("dark")})
        )
        return evaluate_gate(
            "covert_rendezvous",
            has_sustained_rendezvous_episode=has_rendezvous,
            independent_irregularities=irregularities,
        )
    if hypothesis_type == "position_spoofing":
        implausible = any(
            e.metadata.get("anomaly_type") in {"position_jump", "circle_spoof", "static_spoof"}
            for e in events
        )
        classifications = [
            e.metadata.get("ais_integrity_classification") for e in events
            if isinstance(e.metadata.get("ais_integrity_classification"), dict)
        ]
        counter_checked = any(
            c.get("label") not in (None, "not_alertable") for c in classifications
        )
        return evaluate_gate(
            "position_spoofing",
            implausible_movement=implausible,
            reproducible_inputs=True,  # derived from deterministic AIS track data
            counter_evidence_checked=counter_checked,
        )
    if hypothesis_type == "infrastructure_pattern":
        dwell = any(e.metadata.get("loiter_minutes") for e in events)
        corroboration = tuple(
            sorted({"sanctions_match" for e in events if e.metadata.get("sanctions_matched")})
        )
        return evaluate_gate(
            "infrastructure_pattern",
            dwell_or_route_repetition=dwell, independent_corroboration=corroboration,
        )
    return False, f"no gate wired for hypothesis_type={hypothesis_type!r}"


def evaluate_episode(episode: dict[str, Any]) -> Optional[InvestigationHypothesis]:
    """Create-or-update the persisted InvestigationHypothesis for one
    build_episodes() episode, or return None when this episode's family
    has no wired gate, carries no usable subject, or fails its gate."""
    props = episode.get("properties") or {}
    hypothesis_type = _FAMILY_HYPOTHESIS_TYPE.get(str(props.get("episode_family") or ""))
    if hypothesis_type is None:
        return None
    subject_ids = tuple(str(s) for s in (props.get("subject_ids") or ()) if s)
    if not subject_ids:
        return None

    signal_ids = tuple(str(s) for s in (props.get("related_signal_ids") or ()) if s)
    events = [e for e in (intel_store.get(sid) for sid in signal_ids) if e is not None]
    if not events:
        return None

    eligible, _reason = _evaluate_gate_for_family(hypothesis_type, events)
    if not eligible:
        return None

    hypothesis_id = f"hyp:{hypothesis_type}:{props.get('episode_id')}"
    reason_codes = tuple(sorted({
        str(e.metadata.get("anomaly_type") or "") for e in events if e.metadata.get("anomaly_type")
    }))

    existing = get_hypothesis(hypothesis_id)
    if existing is None:
        hyp = new_hypothesis(hypothesis_id, hypothesis_type, subject_ids)
        hyp = replace(hyp, evidence_stage="derived")
    else:
        hyp = existing
    hyp = replace(hyp, reason_codes=reason_codes, evidence_links=signal_ids)

    if hyp.state == "candidate" and len(signal_ids) >= _MIN_EVIDENCE_FOR_COLLECTING:
        hyp = transition(hyp, "collecting", actor="hypothesis_engine")

    save_hypothesis(hyp)
    return hyp
