# SPDX-License-Identifier: AGPL-3.0-or-later
"""Production audit endpoints (docs/updates.md P0.1).

Analyst-only (auth-gated the same way as /api/v1/intel, /api/v1/cases,
etc. -- see core.api.main's authorization_gate READ_ROLES prefix list,
which already names /api/v1/audit). Never a public route: a truth-table
row can carry a source name and case timing that shouldn't be exposed
outside the operator surface, even though it carries no raw sensitive
Humanitarian text (docs/fixes.md M11's "no raw text in metric/log
labels" guarantee extends here by the same reasoning).
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/humanitarian-truth-table")
async def humanitarian_truth_table(limit: int = Query(200, ge=1, le=1000)):
    """docs/updates.md P0.1: one row per visible Humanitarian case,
    cross-referencing IntelEventDB, DriftResultDB, the real public
    projections and source health -- with an explicit anomaly-flag list
    per row and an explicit list of flags today's schema cannot compute
    yet (never silently omitted).
    """
    from core.intel.humanitarian_truth_table import run_humanitarian_truth_table_audit

    result = run_humanitarian_truth_table_audit(limit=limit)
    return {
        **result,
        "rows": [asdict(row) for row in result["rows"]],
    }


@router.get("/humanitarian-incidents/{incident_id}")
async def humanitarian_incident(incident_id: str):
    """docs/updates.md P0.6: "public timer can be reconstructed from API
    fields with no hidden frontend inference" -- the canonical incident's
    typed timestamps (reported_at/last_update_at/state_changed_at/
    resolved_at/archived_at) plus its full lifecycle transition audit
    trail (P0.5), straight from HumanitarianIncidentDB/
    IncidentTransitionDB.
    """
    from core.intel.humanitarian_incident import get_incident, list_transitions

    incident = get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {**incident, "transitions": list_transitions(incident_id)}


@router.get("/source-registry")
async def source_registry_catalog():
    """docs/updates.md P1.1: "what SeaCommons is watching" -- descriptive
    catalog (family/coverage/languages/collection method/independence
    group/known limitations) joined against live operational health.
    Never a single reliability score (updates.md P1.1: "source
    reliability is contextual metadata, not one global truth score").
    """
    from core.intel.source_catalog import get_source_registry_catalog

    return {"sources": get_source_registry_catalog()}


@router.get("/coverage-matrix")
async def coverage_matrix(lookback_hours: int = Query(168, ge=1, le=8760)):
    """docs/updates.md P1.2: per-region (Western/Central/Eastern
    Mediterranean, Aegean, Adriatic/Ionian, Atlantic/Canary route)
    coverage -- active/healthy sources, source-family mix, single-family
    dependency risk, last successful fetch. Zero-event regions are
    listed explicitly, never omitted -- "the platform must expose its
    observable universe and gaps."
    """
    from dataclasses import asdict

    from core.intel.coverage_matrix import build_coverage_matrix

    matrix = build_coverage_matrix(lookback_hours=lookback_hours)
    return asdict(matrix)


@router.get("/coverage-change-log")
async def coverage_change_log(source_name: str | None = None, limit: int = Query(200, ge=1, le=1000)):
    """docs/updates.md P1.3: "version the coverage profile" -- the
    append-only log of when a source's coverage changed (added/removed/
    method_changed/coverage_break) and why, per source. Never edited,
    only appended to.
    """
    from dataclasses import asdict

    from core.intel.coverage_change_log import get_coverage_change_log

    events = get_coverage_change_log(source_name=source_name, limit=limit)
    return {"events": [asdict(e) for e in events]}


@router.get("/preservation-summary")
async def preservation_summary(limit: int = Query(5000, ge=1, le=50000)):
    """docs/updates.md Section 6: "Preservation and public publication
    are separate policies" -- real counts of source_observations by
    preservation_status (not_applicable/preserved/restricted). No
    adapter populates an archive reference yet, so today this honestly
    reports mostly not_applicable -- see core.intel.preservation's own
    module docstring for the named non-goal.
    """
    from core.intel.preservation import summarize_preservation_status

    return {"counts": summarize_preservation_status(limit=limit)}


@router.get("/correlation-decisions/{observation_id}")
async def correlation_decisions(observation_id: str):
    """docs/updates.md P2.1: candidate incident pairings surfaced for
    analyst review -- never an automatic merge. See
    core.intel.correlation's NOT_YET_COMPUTABLE for candidate-generation
    signals not yet implemented.
    """
    from dataclasses import asdict

    from core.intel.correlation import NOT_YET_COMPUTABLE, get_correlation_decisions

    decisions = get_correlation_decisions(observation_id)
    return {
        "decisions": [asdict(d) for d in decisions],
        "not_yet_computable_signals": NOT_YET_COMPUTABLE,
    }


@router.get("/lineage/{observation_id}")
async def lineage(observation_id: str):
    """docs/updates.md P2.2: derivation/quotation edges detected for
    this observation -- see core.intel.circular_reporting's
    NOT_YET_COMPUTABLE for what this cannot yet detect (partial
    quotation, exact multi-hop chain order).
    """
    from dataclasses import asdict

    from core.intel.circular_reporting import NOT_YET_COMPUTABLE as LINEAGE_NOT_YET_COMPUTABLE
    from core.intel.circular_reporting import get_lineage

    edges = get_lineage(observation_id)
    return {
        "edges": [asdict(e) for e in edges],
        "not_yet_computable_signals": LINEAGE_NOT_YET_COMPUTABLE,
    }


@router.get("/entity-graph/{entity_type}/{canonical_key}")
async def entity_graph(entity_type: str, canonical_key: str):
    """docs/updates.md P2.3: an entity's relationships, by (entity_type,
    canonical_key). See core.intel.entity_graph's NOT_YET_WIRED for
    which named entity/relation types have no producer yet.
    """
    from dataclasses import asdict

    from core.intel.entity_graph import (
        NOT_YET_WIRED,
        entity_id as compute_entity_id,
        get_relationships,
    )

    eid = compute_entity_id(entity_type, canonical_key)
    relationships = get_relationships(eid)
    return {
        "entity_id": eid,
        "relationships": [asdict(r) for r in relationships],
        "not_yet_wired": NOT_YET_WIRED,
    }

@router.get("/incident-watches")
async def incident_watches(limit: int = Query(200, ge=1, le=1000)):
    """Operator-only IncidentWatch status without sensitive watch profiles."""
    from core.intel.incident_watch import list_watch_summaries

    return {"watches": list_watch_summaries(limit=limit)}

