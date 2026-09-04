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
