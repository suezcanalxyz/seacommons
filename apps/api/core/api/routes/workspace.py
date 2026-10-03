"""Private partner records. Authentication is enforced here even in local/demo profiles."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from core.db.models import WorkspaceRecord, WorkspaceRevision
from core.db.session import session_scope
from core.partner_security import require_partner

router = APIRouter(prefix="/api/v1/workspace", tags=["partner workspace"])


class RecordInput(BaseModel):
    kind: Literal["document", "deck", "analysis", "workflow", "milestone"]
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=200_000)
    status: Literal["draft", "planned", "in_progress", "blocked", "complete", "archived"] = "draft"
    owner: str = Field(default="", max_length=200)
    due_on: date | None = None


class RecordUpdate(RecordInput):
    version: int = Field(ge=1)


def _no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"


def _serialize(row: WorkspaceRecord, *, content: bool = True) -> dict:
    fields = ["id", "kind", "title", "status", "owner", "due_on", "version", "created_at", "updated_at"]
    result = {field: getattr(row, field) for field in fields}
    if content:
        result["body"] = row.body
    return result


def _history(session, row: WorkspaceRecord, actor: str) -> None:
    session.add(WorkspaceRevision(
        id=str(uuid4()), record_id=row.id, organization_id=row.organization_id,
        version=row.version, actor=actor, timestamp=row.updated_at, snapshot=_serialize(row),
    ))


@router.get("/me")
def me(request: Request, response: Response):
    partner = require_partner(request)
    _no_cache(response)
    return {"subject": partner.subject, "email": partner.email, "organization_id": partner.organization_id,
            "role": partner.role, "can_edit": partner.can_edit}


@router.get("/records")
def records(request: Request, response: Response, offset: int = 0, limit: int = 100):
    partner = require_partner(request)
    if offset < 0 or not 1 <= limit <= 200:
        raise HTTPException(422, "Invalid page")
    _no_cache(response)
    with session_scope() as session:
        rows = session.scalars(select(WorkspaceRecord).where(
            WorkspaceRecord.organization_id == partner.organization_id
        ).order_by(WorkspaceRecord.updated_at.desc(), WorkspaceRecord.id).offset(offset).limit(limit + 1)).all()
        return {"items": [_serialize(row, content=False) for row in rows[:limit]],
                "has_more": len(rows) > limit}


@router.get("/records/{record_id}")
def record(record_id: str, request: Request, response: Response):
    partner = require_partner(request)
    _no_cache(response)
    with session_scope() as session:
        row = session.scalar(select(WorkspaceRecord).where(
            WorkspaceRecord.id == record_id, WorkspaceRecord.organization_id == partner.organization_id
        ))
        if row is None:
            raise HTTPException(404, "Record not found")
        return _serialize(row)


@router.post("/records", status_code=201)
def create(data: RecordInput, request: Request, response: Response):
    partner = require_partner(request, edit=True)
    if not data.title.strip():
        raise HTTPException(422, "A title is required")
    _no_cache(response)
    now = datetime.now(timezone.utc).isoformat()
    with session_scope() as session:
        row = WorkspaceRecord(
            id=str(uuid4()), organization_id=partner.organization_id,
            **data.model_dump(exclude={"due_on"}), due_on=data.due_on.isoformat() if data.due_on else None,
            version=1, created_by=partner.subject, updated_by=partner.subject,
            created_at=now, updated_at=now,
        )
        session.add(row)
        session.flush()
        _history(session, row, partner.subject)
        return _serialize(row)


@router.put("/records/{record_id}")
def edit_record(record_id: str, data: RecordUpdate, request: Request, response: Response):
    partner = require_partner(request, edit=True)
    if not data.title.strip():
        raise HTTPException(422, "A title is required")
    _no_cache(response)
    with session_scope() as session:
        row = session.scalar(select(WorkspaceRecord).where(
            WorkspaceRecord.id == record_id, WorkspaceRecord.organization_id == partner.organization_id
        ))
        if row is None:
            raise HTTPException(404, "Record not found")
        values = data.model_dump(exclude={"version", "due_on"})
        values.update(due_on=data.due_on.isoformat() if data.due_on else None,
                      version=data.version + 1, updated_by=partner.subject,
                      updated_at=datetime.now(timezone.utc).isoformat())
        result = session.execute(update(WorkspaceRecord).where(
            WorkspaceRecord.id == record_id, WorkspaceRecord.organization_id == partner.organization_id,
            WorkspaceRecord.version == data.version,
        ).values(**values))
        if result.rowcount != 1:
            raise HTTPException(409, "This record changed. Reload it before saving.")
        session.refresh(row)
        _history(session, row, partner.subject)
        return _serialize(row)


@router.get("/records/{record_id}/history")
def history(record_id: str, request: Request, response: Response):
    partner = require_partner(request)
    _no_cache(response)
    with session_scope() as session:
        row = session.scalar(select(WorkspaceRecord).where(
            WorkspaceRecord.id == record_id, WorkspaceRecord.organization_id == partner.organization_id
        ))
        if row is None:
            raise HTTPException(404, "Record not found")
        rows = session.scalars(select(WorkspaceRevision).where(
            WorkspaceRevision.record_id == record_id,
            WorkspaceRevision.organization_id == partner.organization_id,
        ).order_by(WorkspaceRevision.version.desc()).limit(100)).all()
        return {"items": [{"version": entry.version, "timestamp": entry.timestamp,
                           "actor": entry.actor, "snapshot": entry.snapshot} for entry in rows]}
