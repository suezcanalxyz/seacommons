# SPDX-License-Identifier: AGPL-3.0-or-later
"""Futures operator Intelligence. Same canonical DB aggregations as the operator dashboard.

Never proxy an operator gateway password or expose private case geometry to viewers.
OAuth/OIDC operator role checked per request, including for aggregate endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from core.security import require_roles
from core.api.routes import operator_ingestion

router = APIRouter(prefix="/api/v1/futures/intelligence", tags=["futures-intelligence"])
OPERATOR_ROLES = {"operator", "administrator"}


@router.get("/recent")
def recent(request: Request, hours: int = Query(24, ge=1, le=168)):
    require_roles(request, OPERATOR_ROLES)
    data = operator_ingestion._overview_payload(hours)
    return {"scope": "operator", "period": "rolling", **data}


@router.get("/overall")
def overall(request: Request):
    require_roles(request, OPERATOR_ROLES)
    return {"scope": "operator", **operator_ingestion._overall_payload()}
