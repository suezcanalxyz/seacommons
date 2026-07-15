from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from core.audit import record
from core.db.models import CaseDB, DeletionRequestDB, MembershipDB, OrganizationDB
from core.db.session import session_scope
from core.security import authenticate

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=256)
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
class MembershipCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=256); role: str = "member"
class DeletionCreate(BaseModel):
    organization_id: str | None = None; resource_type: str = Field(max_length=64)
    resource_id: str = Field(max_length=64); reason: str = Field(min_length=10, max_length=5000)

def actor(request: Request) -> str:
    principal = authenticate(request); return principal.subject if principal else "unknown"

@router.post("/organizations", status_code=201)
def create_organization(body: OrganizationCreate, request: Request) -> dict:
    row = OrganizationDB(organization_id=str(uuid.uuid4()), name=body.name, slug=body.slug)
    with session_scope() as db:
        if db.execute(select(OrganizationDB).where(OrganizationDB.slug == body.slug)).scalar_one_or_none(): raise HTTPException(409, "Organization slug already exists")
        db.add(row); record(db, actor=actor(request), action="organization.created", resource_type="organization", resource_id=row.organization_id)
        db.flush(); return {c.name: getattr(row, c.name) for c in row.__table__.columns}

@router.post("/organizations/{organization_id}/members", status_code=201)
def add_member(organization_id: str, body: MembershipCreate, request: Request) -> dict:
    if body.role not in {"member", "operator", "manager", "data_steward"}: raise HTTPException(422, "Invalid membership role")
    with session_scope() as db:
        if db.get(OrganizationDB, organization_id) is None: raise HTTPException(404, "Organization not found")
        row = db.get(MembershipDB, (organization_id, body.subject))
        if row is None: row = MembershipDB(organization_id=organization_id, subject=body.subject, role=body.role); db.add(row)
        else: row.role = body.role
        record(db, actor=actor(request), action="membership.updated", resource_type="organization", resource_id=organization_id, data={"subject": body.subject, "role": body.role})
        return {"organization_id": organization_id, "subject": body.subject, "role": body.role}

@router.post("/deletion-requests", status_code=201)
def request_deletion(body: DeletionCreate, request: Request) -> dict:
    row = DeletionRequestDB(request_id=str(uuid.uuid4()), organization_id=body.organization_id, resource_type=body.resource_type, resource_id=body.resource_id, reason=body.reason, requested_by=actor(request))
    with session_scope() as db:
        db.add(row); record(db, actor=row.requested_by, action="deletion.requested", resource_type=body.resource_type, resource_id=body.resource_id)
        db.flush(); return {c.name: getattr(row, c.name) for c in row.__table__.columns}

@router.post("/retention/scan")
def scan_retention(request: Request) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None); created = 0
    with session_scope() as db:
        cases = db.execute(select(CaseDB).where(CaseDB.retention_until <= now, CaseDB.legal_hold == 0, CaseDB.status.in_(["resolved", "closed"]))).scalars().all()
        for case in cases:
            exists = db.execute(select(DeletionRequestDB).where(DeletionRequestDB.resource_type == "case", DeletionRequestDB.resource_id == case.case_id, DeletionRequestDB.status == "pending")).scalar_one_or_none()
            if exists: continue
            db.add(DeletionRequestDB(request_id=str(uuid.uuid4()), organization_id=case.organization_id, resource_type="case", resource_id=case.case_id, reason="Retention period expired", requested_by="system:retention")); created += 1
        record(db, actor=actor(request), action="retention.scanned", resource_type="system", resource_id="retention", data={"created": created})
    return {"candidates": len(cases), "deletion_requests_created": created}

@router.get("/deletion-requests")
def list_deletion_requests() -> list[dict]:
    with session_scope() as db:
        rows = db.execute(select(DeletionRequestDB).order_by(DeletionRequestDB.created_at.desc()).limit(200)).scalars().all()
        return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in rows]
