# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewed documentary dependency edges for maritime attack correlation.

A charterer's owner-sourced update, a syndicated alert, or a quotation
cannot be a second originating witness. This module does not fetch pages,
infer dependencies from common wording, write data, or authorize publication.
Only a separately reviewed and content-hashed document can supply an edge.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
import re

from core.intel.maritime_attack_correlation import (
    IncidentClaim, _canonical_source_url, _utc,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RELATIONS = frozenset({
    "owner_notified_charterer", "quotes_original", "syndicated_from",
    "reprinted_from",
})


@dataclass(frozen=True)
class ReviewedRelay:
    relay_claim_id: str
    origin_claim_id: str
    relay_source_url: str
    origin_source_url: str
    evidence_url: str
    document_sha256: str
    relation: str
    reviewed_by: str
    reviewed_at: datetime
    captured_at: datetime


@dataclass(frozen=True)
class RelayLineageReview:
    edges: tuple[tuple[str, str], ...] = ()
    rejected: tuple[str, ...] = ()
    publication_allowed: bool = False


def reviewed_relay_edges(
    claims: Sequence[IncidentClaim], relays: Sequence[ReviewedRelay],
) -> RelayLineageReview:
    """Return auditable derived->origin edges, rejecting ambiguous inputs.

    This verifies *documentary attribution*, not whether either original
    report is true or independent of all other sources. If a dependency
    cannot be tied to an exact reviewed source snapshot, fail closed.
    """
    by_id: dict[str, IncidentClaim] = {}
    for claim in claims:
        if not claim.claim_id or (
            claim.claim_id in by_id and by_id[claim.claim_id] != claim
        ):
            return RelayLineageReview(rejected=("conflicting_claim_identifiers",))
        by_id[claim.claim_id] = claim
    accepted: set[tuple[str, str]] = set()
    rejected: list[str] = []
    for index, relay in enumerate(relays):
        reason = ""
        if not isinstance(relay, ReviewedRelay):
            reason = "invalid_relay_record"
        elif (relay.relay_claim_id == relay.origin_claim_id
              or relay.relay_claim_id not in by_id
              or relay.origin_claim_id not in by_id):
            reason = "unknown_or_self_referential_claim"
        elif relay.relation not in _RELATIONS:
            reason = "unsupported_dependency_relation"
        elif (by_id[relay.relay_claim_id].published_at is None
              or by_id[relay.origin_claim_id].published_at is None):
            # A charterer can hear from an owner before the owner's later
            # press release. Never invent an edge to that *later document*.
            reason = "dependency_publication_clock_missing"
        elif (_utc(by_id[relay.origin_claim_id].published_at)
              > _utc(by_id[relay.relay_claim_id].published_at)):
            reason = "origin_document_postdates_relay"
        elif not relay.reviewed_by.strip() or not _SHA256.fullmatch(relay.document_sha256):
            reason = "unreviewed_or_unhashed_document"
        else:
            source = _canonical_source_url(relay.relay_source_url)
            origin = _canonical_source_url(relay.origin_source_url)
            evidence = _canonical_source_url(relay.evidence_url)
            if (not source or not origin or source == origin
                    or source != _canonical_source_url(by_id[relay.relay_claim_id].source_url)
                    or origin != _canonical_source_url(by_id[relay.origin_claim_id].source_url)
                    or evidence != source):
                reason = "source_url_provenance_mismatch"
            else:
                try:
                    captured = _utc(relay.captured_at)
                    reviewed = _utc(relay.reviewed_at)
                    if reviewed < captured:
                        reason = "review_predates_capture"
                except (TypeError, ValueError, AttributeError):
                    reason = "invalid_review_timestamp"
        if reason:
            rejected.append(f"{index}:{reason}")
        else:
            accepted.add((relay.relay_claim_id, relay.origin_claim_id))
    return RelayLineageReview(
        edges=tuple(sorted(accepted)),
        rejected=tuple(rejected),
    )
