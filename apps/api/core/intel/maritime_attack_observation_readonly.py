# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded staging read path: reviewed SourceObservation -> attack candidate.

No extraction from raw payload, no collector, scheduler, write, migration or
publication. An incomplete batch fails closed; the caller owns the read-only
database session and the human review of structured incident extractions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

from core.intel.maritime_attack_correlation import (
    Correlation, IncidentClaim, VesselRef, claim_from_source_observation,
)
from core.intel.maritime_attack_lineage_readonly import correlate_with_verified_lineage


@dataclass(frozen=True)
class ObservationCorrelationResult:
    correlation: Correlation | None
    requested_ids: tuple[str, ...]
    loaded_count: int
    blocked_reasons: tuple[str, ...] = ()


def correlate_reviewed_observations(
    subject: VesselRef,
    observation_ids: Sequence[str],
    reviewed_extractions: Mapping[str, Mapping[str, object]],
    fetch_observations: Callable[[tuple[str, ...]], Iterable[object]],
    fetch_lineage: Callable[[tuple[str, ...]], Iterable[object]],
    *,
    max_observations: int = 32,
) -> ObservationCorrelationResult:
    """Correlate ONLY explicitly selected, operator-reviewed observation IDs.

    Extraction is provided by a separate trusted review process, not guessed
    from raw source text. The function never selects an arbitrary recent news
    item or scans a whole table. Missing, duplicated or unreviewed rows block
    the entire evaluation rather than silently shrinking the evidence set.
    """
    ids = tuple(str(x).strip() for x in observation_ids)
    if max_observations < 1 or not ids or len(ids) > max_observations:
        return ObservationCorrelationResult(None, ids, 0, ("invalid_batch_size",))
    if any(not x for x in ids) or len(set(ids)) != len(ids):
        return ObservationCorrelationResult(None, ids, 0, ("invalid_observation_ids",))
    if any(not isinstance(reviewed_extractions.get(x), Mapping)
           or reviewed_extractions[x].get("reviewed") is not True
           or not str(reviewed_extractions[x].get("reviewed_by") or "").strip()
           for x in ids):
        return ObservationCorrelationResult(None, ids, 0, ("unreviewed_extraction",))

    rows = list(fetch_observations(ids))
    if len(rows) > max_observations:
        return ObservationCorrelationResult(None, ids, len(rows), ("observation_row_limit",))
    found: dict[str, object] = {}
    for row in rows:
        key = str(getattr(row, "observation_id", "") or "")
        if key not in ids or key in found:
            return ObservationCorrelationResult(None, ids, len(rows), ("unexpected_or_duplicate_row",))
        found[key] = row
    if len(found) != len(ids):
        return ObservationCorrelationResult(None, ids, len(rows), ("missing_observations",))

    claims: list[IncidentClaim] = []
    for identifier in sorted(ids):
        observation = found[identifier]
        # Humanitarian distress/drift is a separate domain. Never reclassify
        # it as a military attack through this staging adapter.
        if str(getattr(observation, "service", "")).lower() == "humanitarian":
            return ObservationCorrelationResult(None, ids, len(rows), ("humanitarian_domain_excluded",))
        try:
            claim = claim_from_source_observation(
                observation, dict(reviewed_extractions[identifier])
            )
        except (TypeError, ValueError, OverflowError):
            return ObservationCorrelationResult(None, ids, len(rows), ("invalid_extraction:" + identifier,))
        if claim is None:
            return ObservationCorrelationResult(None, ids, len(rows), ("not_an_incident_claim:" + identifier,))
        claims.append(claim)

    # The existing lineage adapter is fail-closed on incomplete ancestry.
    # It also never publishes even a fully corroborated result.
    correlation = correlate_with_verified_lineage(
        subject, claims, fetch_lineage
    )
    return ObservationCorrelationResult(correlation, ids, len(rows))


def correlate_reviewed_db_observations(
    subject: VesselRef,
    observation_ids: Sequence[str],
    reviewed_extractions: Mapping[str, Mapping[str, object]],
    db: object,
    *,
    max_observations: int = 32,
) -> ObservationCorrelationResult:
    """Use caller-supplied read-only SQLAlchemy session and canonical tables.

    This is an opt-in staging entry point, not wired to LIVE/PLAY or an
    automatic collector. Query limits bound work even if the caller errs.
    """
    from core.db.models import LineageEdgeDB, SourceObservationDB

    def fetch_observations(ids: tuple[str, ...]) -> Iterable[object]:
        return (
            db.query(SourceObservationDB)
            .filter(SourceObservationDB.observation_id.in_(ids))
            .order_by(SourceObservationDB.observation_id)
            .limit(max_observations + 1)
            .all()
        )

    def fetch_lineage(frontier: tuple[str, ...]) -> Iterable[object]:
        return (
            db.query(LineageEdgeDB)
            .filter(LineageEdgeDB.from_observation_id.in_(frontier))
            .order_by(LineageEdgeDB.from_observation_id, LineageEdgeDB.to_observation_id)
            .limit(1025)
            .all()
        )

    return correlate_reviewed_observations(
        subject, observation_ids, reviewed_extractions,
        fetch_observations, fetch_lineage,
        max_observations=max_observations,
    )
