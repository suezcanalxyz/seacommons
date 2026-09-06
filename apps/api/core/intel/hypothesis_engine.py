# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live Observation → persisted Episode → InvestigationHypothesis wiring.

V1 persists every bounded maritime episode before hypothesis evaluation.
Low-specificity hypotheses require the episode-level independent-evidence
gate; detector count never substitutes for source independence. High-
specificity spoofing may remain a candidate on one lineage but cannot
advance to collecting without corroboration.

Legacy hypothesis rows are never relinked. New rows use a versioned ID
(`hyp:v1:...`) and always carry a non-null episode_id.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from core.intel.episode_store import save_episode
from core.intel.hypothesis import InvestigationHypothesis, new_hypothesis, transition
from core.intel.hypothesis_eligibility import evaluate_hypothesis_eligibility
from core.intel.hypothesis_store import get_hypothesis, save_hypothesis
from core.intel.store import IntelEvent, intel_store


def event_to_episode_input_feature(event: IntelEvent) -> Optional[dict[str, Any]]:
    """Build the internal feature used by the bounded episode builder."""
    mmsi = str(event.linked_mmsi or "").strip()
    if len(mmsi) != 9 or not mmsi.isdigit():
        return None
    coordinates = [event.lon, event.lat] if event.lat is not None and event.lon is not None else []
    metadata = event.metadata or {}
    parent_ids = tuple(str(v) for v in (metadata.get("contributing") or ()) if v)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": coordinates},
        "properties": {
            "id": event.id,
            "timestamp_utc": event.timestamp_utc,
            "linked_mmsi": mmsi,
            "anomaly_type": metadata.get("anomaly_type"),
            "ais_nav_status_kind": metadata.get("ais_nav_status_kind"),
            "episode_family": metadata.get("episode_family"),
            "severity": event.severity,
            "source": event.source,
            "observation_ids": list(parent_ids or (event.id,)),
            "feature_ids": [event.id] if parent_ids else [],
            "incident_lifecycle": metadata.get("incident_lifecycle"),
            "behaviour_context": metadata.get("behaviour_context"),
            "alternative_explanations": metadata.get("alternative_explanations"),
        },
    }


def evaluate_episode(episode: dict[str, Any]) -> Optional[InvestigationHypothesis]:
    """Persist the episode, then create/update a v1 hypothesis only when eligible."""
    props = episode.get("properties") or {}
    episode_id = str(props.get("episode_id") or "")
    subject_ids = tuple(str(s) for s in (props.get("subject_ids") or ()) if s)
    if not episode_id or not subject_ids:
        return None

    # Persistence precedes interpretation: an episode remains auditable even
    # when it is benign, unclassified, Safety-only, or hypothesis-ineligible.
    save_episode(episode)

    signal_ids = tuple(str(s) for s in (props.get("related_signal_ids") or ()) if s)
    events = [e for e in (intel_store.get_durable(sid) for sid in signal_ids) if e is not None]
    if not events:
        return None

    decision = evaluate_hypothesis_eligibility(episode, events)
    if not decision.eligible or decision.hypothesis_type is None:
        return None

    hypothesis_type = decision.hypothesis_type
    hypothesis_id = f"hyp:v1:{hypothesis_type}:{episode_id}"
    existing = get_hypothesis(hypothesis_id)
    if existing is None:
        hyp = new_hypothesis(
            hypothesis_id,
            hypothesis_type,
            subject_ids,
            episode_id=episode_id,
        )
    else:
        if existing.episode_id != episode_id:
            raise ValueError("v1 hypothesis episode identity mismatch")
        hyp = existing

    hyp = replace(
        hyp,
        reason_codes=decision.reason_codes,
        counter_indicators=decision.counter_indicators,
        evidence_links=signal_ids,
        evidence_stage=decision.evidence_stage,
    )

    if hyp.state == "candidate" and decision.may_advance_collecting:
        from core.observability import record_hypothesis_transition

        hyp = transition(hyp, "collecting", actor="hypothesis_engine_v1")
        record_hypothesis_transition(hyp.hypothesis_type, hyp.state)

    save_hypothesis(hyp)
    return hyp
