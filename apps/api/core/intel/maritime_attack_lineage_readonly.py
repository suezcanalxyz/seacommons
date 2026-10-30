# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only canonical lineage adapter for staging maritime-attack correlation.

No collector, scheduler, database mutation, incident publication or migration.
The caller supplies a database session; this module never creates or commits one.
A truncated or unverified derivation graph fails closed to operator review.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Callable, Iterable, Sequence

from core.intel.maritime_attack_correlation import (
    AISFix, AISGap, Correlation, IncidentClaim, VesselRef, correlate,
)

# Current canonical detector only verifies verbatim payload matches.
# Never treat a mere citation/quotation as proven independent reporting.
_VERIFIED_METHODS = frozenset({"v0_exact_payload_hash_match", "operator_verified"})
_CANDIDATE_COLOR = "maritime_incident_candidate_orange"


@dataclass(frozen=True)
class LineageResult:
    edges: tuple[tuple[str, str], ...]
    complete: bool
    reason: str = ""
    visited_nodes: int = 0



def _has_derivation_cycle(edges: Iterable[tuple[str, str]]) -> bool:
    """A derived_from chain must be acyclic; cyclic provenance is untrustworthy.

    Traverse only the bounded graph already fetched from canonical lineage.
    No database reads, inference from source labels, or recursion are needed.
    """
    ancestors: dict[str, set[str]] = {}
    for derived, original in edges:
        ancestors.setdefault(derived, set()).add(original)
    complete: set[str] = set()
    active: set[str] = set()
    for root in sorted(ancestors):
        if root in complete:
            continue
        stack = [(root, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                active.discard(node)
                complete.add(node)
                continue
            if node in active:
                return True
            if node in complete:
                continue
            active.add(node)
            stack.append((node, True))
            for ancestor in sorted(ancestors.get(node, ()), reverse=True):
                stack.append((ancestor, False))
    return False


def load_verified_lineage(
    claim_ids: Sequence[str],
    fetch_rows: Callable[[tuple[str, ...]], Iterable[object]],
    *,
    max_depth: int = 8,
    max_nodes: int = 256,
    max_edges: int = 1024,
) -> LineageResult:
    """Follow derived_from edges to original ancestors, including intermediates.

    fetch_rows(frontier) returns rows with from_observation_id in frontier,
    each with from_observation_id, to_observation_id, relation, confidence
    and method_version. Limits are hard safety boundaries, not evidence of
    independence. Any unknown/low-confidence edge forces human review.
    """
    if min(max_depth, max_nodes, max_edges) < 1:
        raise ValueError("Lineage bounds must be positive")
    visited = {str(identifier).strip() for identifier in claim_ids if str(identifier).strip()}
    if len(visited) > max_nodes:
        return LineageResult((), False, "lineage_node_limit", len(visited))
    if not visited:
        return LineageResult((), True, visited_nodes=0)
    frontier = set(visited)
    edges: set[tuple[str, str]] = set()
    for depth in range(max_depth):
        new_nodes: set[str] = set()
        # The canonical table indexes from_observation_id; query only the
        # current frontier rather than scanning the whole lineage table.
        for row in fetch_rows(tuple(sorted(frontier))):
            derived = str(getattr(row, "from_observation_id", "") or "").strip()
            original = str(getattr(row, "to_observation_id", "") or "").strip()
            relation = str(getattr(row, "relation", "") or "")
            method = str(getattr(row, "method_version", "") or "")
            confidence = getattr(row, "confidence", None)
            if not derived or not original or derived not in frontier:
                return LineageResult(tuple(sorted(edges)), False, "invalid_lineage_row", len(visited))
            if (relation != "derived_from" or method not in _VERIFIED_METHODS
                    or not isinstance(confidence, (int, float))
                    or not isfinite(confidence) or not 0.9 <= confidence <= 1.0):
                return LineageResult(tuple(sorted(edges)), False, "unverified_lineage_edge", len(visited))
            edges.add((derived, original))
            if len(edges) > max_edges:
                return LineageResult(tuple(sorted(edges))[:max_edges], False, "lineage_edge_limit", len(visited))
            if original not in visited:
                new_nodes.add(original)
        if not new_nodes:
            if _has_derivation_cycle(edges):
                return LineageResult(tuple(sorted(edges)), False, "lineage_cycle_detected", len(visited))
            return LineageResult(tuple(sorted(edges)), True, visited_nodes=len(visited))
        if len(visited | new_nodes) > max_nodes:
            return LineageResult(tuple(sorted(edges)), False, "lineage_node_limit", len(visited | new_nodes))
        visited.update(new_nodes)
        if depth == max_depth - 1:
            return LineageResult(tuple(sorted(edges)), False, "lineage_depth_limit", len(visited))
        frontier = new_nodes
    return LineageResult(tuple(sorted(edges)), False, "lineage_depth_limit", len(visited))


def correlate_with_verified_lineage(
    subject: VesselRef,
    claims: Sequence[IncidentClaim],
    fetch_rows: Callable[[tuple[str, ...]], Iterable[object]],
    *,
    ais_fixes: Sequence[AISFix] = (),
    ais_gaps: Sequence[AISGap] = (),
    max_depth: int = 8,
    max_nodes: int = 256,
    max_edges: int = 1024,
) -> Correlation:
    """Staging-only read path: unknown lineage cannot promote PLAY to incident."""
    if not claims:
        return correlate(subject, claims, ais_fixes, ais_gaps)
    lineage = load_verified_lineage(
        [claim.claim_id for claim in claims], fetch_rows,
        max_depth=max_depth, max_nodes=max_nodes, max_edges=max_edges,
    )
    result = correlate(subject, claims, ais_fixes, ais_gaps, lineage_edges=lineage.edges)
    if not lineage.complete:
        return replace(
            result, status="candidate", color_token=_CANDIDATE_COLOR,
            contradicting=result.contradicting + (lineage.reason,),
            publication_allowed=False, requires_operator_review=True,
        )
    return result


def correlate_with_db_lineage(
    subject: VesselRef,
    claims: Sequence[IncidentClaim],
    db: object,
    *,
    ais_fixes: Sequence[AISFix] = (),
    ais_gaps: Sequence[AISGap] = (),
    max_depth: int = 8,
    max_nodes: int = 256,
    max_edges: int = 1024,
) -> Correlation:
    """Use the existing SQLAlchemy session and canonical lineage_edges only.

    The caller must supply a read-only transaction/session. No session_scope
    is opened and no .add(), .flush(), .commit() or SQL writes occur here.
    Database failures propagate: NEVER fall back to unverified corroboration.
    """
    from core.db.models import LineageEdgeDB

    def fetch(frontier: tuple[str, ...]) -> Iterable[object]:
        return (
            db.query(LineageEdgeDB)
            .filter(LineageEdgeDB.from_observation_id.in_(frontier))
            .order_by(LineageEdgeDB.from_observation_id, LineageEdgeDB.to_observation_id)
            .limit(max_edges + 1)
            .all()
        )

    return correlate_with_verified_lineage(
        subject, claims, fetch, ais_fixes=ais_fixes, ais_gaps=ais_gaps,
        max_depth=max_depth, max_nodes=max_nodes, max_edges=max_edges,
    )
