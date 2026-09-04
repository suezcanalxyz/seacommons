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

from fastapi import APIRouter, Query

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
