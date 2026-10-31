# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging-only reconciliation of a later sinking with an existing attack.

This module NEVER infers causation from AIS, proximity or vessel identity.
An explicitly reviewed documentary link is mandatory. It does not create a
second attack, mutate an episode, publish a finding or access the database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from core.intel.maritime_attack_correlation import (
    Correlation, IncidentClaim, VesselRef, _canonical_source_url,
    _chronology_issues, _identity_match, _km, _utc, _valid_imo,
    _valid_mmsi, _validate_claim_location,
)

_CANDIDATE_COLOR = "maritime_incident_candidate_orange"
_SINKING_COLOR = "maritime_sinking_bordeaux"


@dataclass(frozen=True)
class ReviewedOutcomeLink:
    attack_episode_id: str
    attack_claim_id: str
    outcome_claim_id: str
    evidence_claim_id: str
    evidence_url: str
    reviewed_by: str
    relation: str = "reported_outcome_of"
    verified: bool = False


@dataclass(frozen=True)
class OutcomeAssociation:
    status: str  # rejected | candidate_update | corroborated_update
    attack_episode_id: str
    outcome_key: str
    outcome_type: str
    color_token: str
    reason_codes: tuple[str, ...]
    source_evidence: tuple[dict[str, str | None], ...] = ()
    publication_allowed: bool = False
    requires_operator_review: bool = True


def _rejected(link: ReviewedOutcomeLink, reason: str) -> OutcomeAssociation:
    return OutcomeAssociation(
        "rejected", link.attack_episode_id, "", "", "",
        (reason,),
    )


def reconcile_reported_sinking(
    subject: VesselRef,
    attack: IncidentClaim,
    sinking: IncidentClaim,
    attack_correlation: Correlation,
    sinking_correlation: Correlation,
    link: ReviewedOutcomeLink,
    *,
    max_followup_days: int = 14,
) -> OutcomeAssociation:
    """Attach a documented sinking OUTCOME to an existing attack episode.

    Only a trusted, operator-verified documentary relation may establish that
    the later sinking belongs to the earlier attack. Corroboration of each
    event is evaluated separately. Even a corroborated update is NOT public
    and requires a separate publication decision by the existing policy.
    """
    if max_followup_days < 1 or max_followup_days > 30:
        raise ValueError("Invalid outcome follow-up bound")
    if (not link.attack_episode_id.strip()
            or len(link.attack_episode_id) > 128):
        return _rejected(link, "invalid_existing_episode_id")
    if attack.kind != "attack" or sinking.kind != "sinking":
        return _rejected(link, "not_attack_to_sinking")
    if (link.attack_claim_id != attack.claim_id
            or link.outcome_claim_id != sinking.claim_id
            or link.evidence_claim_id != sinking.claim_id):
        return _rejected(link, "review_link_claim_mismatch")
    if (link.verified is not True
            or link.relation != "reported_outcome_of"
            or not link.reviewed_by.strip()
            or _canonical_source_url(link.evidence_url) == ""
            or _canonical_source_url(link.evidence_url)
                != _canonical_source_url(sinking.source_url)):
        return _rejected(link, "missing_verified_documentary_link")
    if (attack.claim_id not in attack_correlation.claim_ids
            or sinking.claim_id not in sinking_correlation.claim_ids
            or attack_correlation.incident_type != "attack"
            or sinking_correlation.incident_type != "sinking"):
        return _rejected(link, "correlation_does_not_include_claim")
    if (attack_correlation.status not in {"candidate", "corroborated"}
            or sinking_correlation.status not in {"candidate", "corroborated"}):
        return _rejected(link, "unusable_correlation_status")
    if ((subject.imo and not _valid_imo(subject.imo))
            or (subject.mmsi and not _valid_mmsi(subject.mmsi))
            or _identity_match(subject, attack.vessel) != "strong"
            or _identity_match(subject, sinking.vessel) != "strong"
            or _identity_match(attack.vessel, sinking.vessel) == "conflict"):
        return _rejected(link, "strong_vessel_identity_required")
    if not all(
        claim.origin_report_id and claim.source_group
        and _canonical_source_url(claim.source_url)
        for claim in (attack, sinking)
    ):
        return _rejected(link, "missing_original_document_provenance")
    try:
        _validate_claim_location(attack)
        _validate_claim_location(sinking)
        attack_at, sinking_at = _utc(attack.occurred_at), _utc(sinking.occurred_at)
        if _chronology_issues(attack) or _chronology_issues(sinking):
            return _rejected(link, "chronology_contradiction")
    except (ValueError, TypeError, AttributeError):
        return _rejected(link, "invalid_event_time_or_position")

    elapsed = (sinking_at - attack_at).total_seconds()
    time_margin = 60 * (attack.time_uncertainty_minutes + sinking.time_uncertainty_minutes)
    if elapsed < -time_margin or elapsed > timedelta(days=max_followup_days).total_seconds() + time_margin:
        return _rejected(link, "outcome_outside_followup_window")
    if attack.lat is not None and sinking.lat is not None:
        # Generous upper bound for a moving vessel; it is only a veto.
        # Geospatial proximity by itself NEVER creates a causal relation.
        max_travel_km = (30 + 95 * max(0.0, elapsed / 3600)
                         + attack.uncertainty_km + sinking.uncertainty_km)
        if _km(attack.lat, attack.lon, sinking.lat, sinking.lon) > max_travel_km:
            return _rejected(link, "implausible_vessel_displacement")

    # A reviewed causal link is not a substitute for independently complete
    # event/source chronology. Even if upstream status labels say corroborated,
    # incomplete publication/receipt clocks or coarse event precision must
    # keep the outcome in operator-review candidate state. This matches the
    # pure correlator's fail-closed provenance and precision gates.
    chronology_complete = all(
        claim.published_at is not None and claim.received_at is not None
        for claim in (attack, sinking)
    )
    precision_qualified = all(
        claim.time_uncertainty_minutes <= (180 if claim.kind == "attack" else 360)
        and (claim.lat is None or claim.uncertainty_km <= 250)
        for claim in (attack, sinking)
    )
    # Uncertainty intervals must establish the ordering, not merely permit
    # it. An outcome can be attached as a candidate when intervals overlap,
    # but cannot be called corroborated if sinking may predate the attack.
    attack_earliest = attack_at - timedelta(minutes=attack.time_uncertainty_minutes)
    attack_latest = attack_at + timedelta(minutes=attack.time_uncertainty_minutes)
    sinking_earliest = sinking_at - timedelta(minutes=sinking.time_uncertainty_minutes)
    sinking_latest = sinking_at + timedelta(minutes=sinking.time_uncertainty_minutes)
    sequence_certain = sinking_earliest > attack_latest
    followup_certain = (sinking_latest - attack_earliest) <= timedelta(
        days=max_followup_days
    )
    corroborated = (attack_correlation.status == "corroborated"
                    and sinking_correlation.status == "corroborated"
                    and chronology_complete and precision_qualified
                    and sequence_certain and followup_certain)
    evidence: list[dict[str, str | None]] = []
    for claim in (attack, sinking):
        evidence.append({
            "claim_id": claim.claim_id,
            "kind": claim.kind,
            "source_url": claim.source_url,
            "source_group": claim.source_group,
            "origin_report_id": claim.origin_report_id,
            "occurred_at": _utc(claim.occurred_at).isoformat(),
            "published_at": _utc(claim.published_at).isoformat()
                if claim.published_at is not None else None,
            "received_at": _utc(claim.received_at).isoformat()
                if claim.received_at is not None else None,
        })
    reasons = [
        "operator_verified_reported_outcome_link",
        "existing_attack_episode_retained",
        "no_second_attack_created",
        "ais_not_causal_evidence",
    ]
    if not chronology_complete:
        reasons.append("outcome_chronology_incomplete")
    if not precision_qualified:
        reasons.append("outcome_precision_insufficient")
    if not sequence_certain:
        reasons.append("outcome_temporal_order_ambiguous")
    if not followup_certain:
        reasons.append("outcome_followup_window_ambiguous")
    if not corroborated:
        reasons.append("independent_corroboration_incomplete")
    reasons.append("publication_requires_separate_review")
    return OutcomeAssociation(
        status="corroborated_update" if corroborated else "candidate_update",
        attack_episode_id=link.attack_episode_id,
        outcome_key=link.attack_episode_id + ":outcome:sinking",
        outcome_type="sinking",
        color_token=_SINKING_COLOR if corroborated else _CANDIDATE_COLOR,
        reason_codes=tuple(reasons),
        source_evidence=tuple(evidence),
    )
