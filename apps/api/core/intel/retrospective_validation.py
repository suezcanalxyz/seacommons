# SPDX-License-Identifier: AGPL-3.0-or-later
"""Versioned adjudication of a single historical claim from qualified evidence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Mapping
from typing import Literal

from core.evidence.cross_modal import CrossModalEvidencePacket, EvidenceReference
from core.intel.alert_recognition_scorer import ClassResult

METHOD = "retrospective-claim-validation/v1"
Relation = Literal["supports", "contradicts", "context"]
Classification = Literal["confirmed", "probable", "uncertain", "false_positive"]
Confidence = Literal["high", "moderate", "low"]


def _utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("an explicit time zone is required")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ClaimEvidence:
    """Evidence already matched to this claim by an authorized research workflow.

    Use context for proximity, unverified identity, and absence of detection.
    A repeated report must use the original lineage, even across modalities.
    """

    reference: EvidenceReference
    relation: Relation
    available_at: datetime

    def __post_init__(self) -> None:
        if self.relation not in {"supports", "contradicts", "context"}:
            raise ValueError("unknown evidence relation")
        if _utc(self.available_at) < _utc(self.reference.observed_at):
            raise ValueError("evidence was available before it was observed")


@dataclass(frozen=True)
class ClaimDossier:
    episode_id: str
    claim_id: str
    cutoff: datetime
    classification: Classification
    confidence: Confidence
    reason: str
    evidence: tuple[ClaimEvidence, ...]
    later_evidence_ids: tuple[str, ...]
    support_groups: tuple[str, ...]
    contradiction_groups: tuple[str, ...]
    reviewed_by: str | None
    review_reason: str | None
    reviewed_at: datetime | None
    method: str = METHOD

    @property
    def suppress_public(self) -> bool:
        """A reviewed refutation can suppress this claim's public projection."""
        return self.classification == "false_positive" and self.reviewed_by is not None


def _groups(items: list[ClaimEvidence], ais_lineages: set[str]) -> tuple[set[str], set[str]]:
    modalities_by_lineage: dict[str, set[str]] = {}
    for item in items:
        ref = item.reference
        if ref.independence_key is None or ref.source_lineage.rsplit(":", 1)[-1] in {"unknown", "unverified"}:
            continue
        group = "ais" if ref.source_lineage in ais_lineages else ref.source_lineage
        modalities_by_lineage.setdefault(group, set()).add(ref.modality)
    # A lineage appearing in several modalities may be a rebroadcast. It
    # cannot supply the modality diversity needed to qualify the decision.
    modalities = {next(iter(modes)) for modes in modalities_by_lineage.values() if len(modes) == 1}
    return set(modalities_by_lineage), modalities


def validate_claim(
    episode_id: str,
    claim_id: str,
    evidence: tuple[ClaimEvidence, ...],
    *,
    cutoff: datetime,
    reviewed_by: str | None = None,
    review_reason: str | None = None,
    reviewed_at: datetime | None = None,
) -> ClaimDossier:
    """Build a private dossier with a conservative, non-calibrated confidence tier."""
    if not episode_id.strip() or not claim_id.strip():
        raise ValueError("episode and claim identifiers are required")
    cutoff = _utc(cutoff)
    reviewed_by = (reviewed_by or "").strip() or None
    review_reason = (review_reason or "").strip() or None
    reviewed_at = _utc(reviewed_at) if reviewed_at is not None else None
    if len({bool(reviewed_by), bool(review_reason), bool(reviewed_at)}) != 1:
        raise ValueError("reviewer, review time and written rationale must be recorded together")
    if reviewed_at is not None and reviewed_at < cutoff:
        raise ValueError("review precedes the dossier cutoff")
    by_id: dict[str, ClaimEvidence] = {}
    for item in evidence:
        key = item.reference.evidence_id
        if key in by_id and by_id[key] != item:
            raise ValueError("conflicting evidence reference")
        by_id[key] = item
    # Reuse the normal packet's identity and size validation.
    packet = CrossModalEvidencePacket(episode_id, tuple(item.reference for item in by_id.values())) if by_id else None
    ordered = tuple(by_id[ref.evidence_id] for ref in packet.evidence) if packet else ()
    eligible = [item for item in ordered if item.available_at <= cutoff]
    later = tuple(item.reference.evidence_id for item in ordered if item.available_at > cutoff)
    ais_lineages = {item.reference.source_lineage for item in eligible if item.reference.modality == "ais"}
    supporting, support_modes = _groups(
        [item for item in eligible if item.relation == "supports"], ais_lineages,
    )
    opposing, opposing_modes = _groups(
        [item for item in eligible if item.relation == "contradicts"], ais_lineages,
    )

    classification: Classification = "uncertain"
    confidence: Confidence = "low"
    reason = "Insufficient qualified, independent evidence available by the cutoff."
    if supporting and opposing:
        reason = "Qualified evidence supports and contradicts the same claim."
    elif len(opposing) >= 2 and len(opposing_modes) >= 2:
        reason = "Independent counterevidence awaits documented review."
        if reviewed_by:
            classification, confidence = "false_positive", "high"
            reason = "Documented review resolved the claim using independent counterevidence."
    elif len(supporting) >= 2 and len(support_modes) >= 2:
        classification, confidence = "probable", "moderate"
        reason = "Independent evidence supports the claim across modalities."
        if reviewed_by:
            classification, confidence = "confirmed", "high"
            reason = "Documented review confirmed the independently supported claim."

    return ClaimDossier(episode_id, claim_id, cutoff, classification, confidence, reason,
                        ordered, later, tuple(sorted(supporting)), tuple(sorted(opposing)),
                        reviewed_by, review_reason, reviewed_at)


@dataclass(frozen=True)
class DetectorComparison:
    baseline: ClassResult
    candidate: ClassResult
    unresolved_truth: int
    baseline_abstentions: int
    candidate_abstentions: int


def compare_detectors(
    truth: Mapping[str, Classification],
    baseline: Mapping[str, bool | None],
    candidate: Mapping[str, bool | None],
) -> DetectorComparison:
    """Score cutoff-consistent detector outputs against independently reviewed labels."""
    if not truth or truth.keys() != baseline.keys() or truth.keys() != candidate.keys():
        raise ValueError("both detectors must cover the same nonempty frozen cohort")
    if set(truth.values()) - {"confirmed", "false_positive", "uncertain", "probable"}:
        raise ValueError("invalid adjudicated outcome")
    summaries = [ClassResult("event_occurrence"), ClassResult("event_occurrence")]
    abstentions = [0, 0]
    unresolved = 0
    for case_id in sorted(truth):
        label = truth[case_id]
        unresolved += label in {"uncertain", "probable"}
        for index, predictions in enumerate((baseline, candidate)):
            decision = predictions[case_id]
            if decision is not None and type(decision) is not bool:
                raise ValueError("detector predictions must be boolean or abstain")
            abstentions[index] += decision is None
            score = summaries[index]
            if label == "confirmed":
                if decision is True:
                    score.true_positives += 1
                else:
                    score.false_negatives += 1
                    score.fn_ids.append(case_id)
            elif label == "false_positive":
                if decision is True:
                    score.false_positives += 1
                    score.fp_ids.append(case_id)
                elif decision is False:
                    score.true_negatives += 1
    return DetectorComparison(summaries[0], summaries[1], unresolved, abstentions[0], abstentions[1])
