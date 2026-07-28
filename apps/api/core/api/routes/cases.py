# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import uuid
import hashlib
import re
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.db.models import AuditLogDB, CaseAccessDB, CaseAttachmentDB, CaseDB, CaseSignalDB, CaseTimelineDB, IngestedSignalDB, MembershipDB
from core.db.session import session_scope
from core.security import authenticate
from core.audit import record
from core.config import config
from core import object_store
from core.notifications import telegram, whatsapp

router = APIRouter(prefix="/api/v1", tags=["cases"])

STATUSES = {"open", "triage", "active", "monitoring", "resolved", "closed"}
PRIORITIES = {"low", "medium", "high", "critical"}


class CaseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=256)
    priority: str = "medium"
    sensitivity: str = "restricted"
    summary: str = Field(default="", max_length=10_000)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    persons: int | None = Field(default=None, ge=0, le=100_000)
    signal_id: str | None = None
    organization_id: str | None = None


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=256)
    status: str | None = None
    priority: str | None = None
    summary: str | None = Field(default=None, max_length=10_000)
    assigned_to: str | None = Field(default=None, max_length=256)


class TimelineCreate(BaseModel):
    event_type: str = Field(default="note", max_length=32)
    body: str = Field(min_length=1, max_length=20_000)
    data: dict = Field(default_factory=dict)


def _actor(request: Request) -> str:
    principal = authenticate(request)
    return principal.subject if principal else "unknown"


def _case(row: CaseDB) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def _principal_org(request: Request) -> str | None:
    principal = authenticate(request)
    if not principal: return None
    return principal.claims.get(config.OIDC_ORGANIZATION_CLAIM) or principal.claims.get("org_id")


def _require_case_access(request: Request, db, row: CaseDB, write: bool = False) -> None:
    if not config.AUTH_ENABLED: return
    principal = authenticate(request)
    if principal and "administrator" in principal.roles: return
    if principal and row.organization_id and _principal_org(request) == row.organization_id:
        membership = db.get(MembershipDB, (row.organization_id, principal.subject))
        if membership and (not write or membership.role in {"operator", "manager", "data_steward"}): return
    grant = db.get(CaseAccessDB, (row.case_id, principal.subject if principal else ""))
    if grant and (not write or grant.permission == "write"): return
    raise HTTPException(403, "No access to this case")


@router.get("/inbox")
def inbox(request: Request, limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    linked = select(CaseSignalDB.signal_id)
    with session_scope() as db:
        query = select(IngestedSignalDB).where(
            ~IngestedSignalDB.signal_id.in_(linked)
        )
        if config.AUTH_ENABLED:
            principal = authenticate(request)
            if principal and "administrator" not in principal.roles:
                query = query.where(
                    IngestedSignalDB.organization_id == _principal_org(request)
                )
        rows = db.execute(
            query.order_by(IngestedSignalDB.received_at.desc()).limit(limit)
        ).scalars().all()
        return [{**row.payload, "received_at": row.received_at} for row in rows]


@router.get("/cases")
def list_cases(request: Request, status: str | None = None, limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    with session_scope() as db:
        query = select(CaseDB)
        if status:
            query = query.where(CaseDB.status == status)
        if config.AUTH_ENABLED:
            principal = authenticate(request)
            if principal and "administrator" not in principal.roles:
                org_id = _principal_org(request)
                query = query.where(CaseDB.organization_id == org_id)
        query = query.order_by(CaseDB.updated_at.desc()).limit(limit)
        return [_case(row) for row in db.execute(query).scalars().all()]


@router.post("/cases", status_code=201)
def create_case(body: CaseCreate, request: Request) -> dict:
    if body.priority not in PRIORITIES:
        raise HTTPException(422, "Invalid priority")
    actor = _actor(request)
    organization_id = body.organization_id or _principal_org(request)
    principal = authenticate(request)
    if config.AUTH_ENABLED:
        if not principal or ("administrator" not in principal.roles and organization_id != _principal_org(request)):
            raise HTTPException(403, "Invalid organization")
    case_id = str(uuid.uuid4())
    with session_scope() as db:
        if body.signal_id:
            signal = db.get(IngestedSignalDB, body.signal_id)
            if signal is None:
                raise HTTPException(404, "Signal not found")
            if (
                config.AUTH_ENABLED
                and principal
                and "administrator" not in principal.roles
                and signal.organization_id != organization_id
            ):
                raise HTTPException(403, "Signal belongs to another organization")
        row = CaseDB(case_id=case_id, organization_id=organization_id, title=body.title, priority=body.priority,
                     sensitivity=body.sensitivity, summary=body.summary, lat=body.lat,
                     lon=body.lon, persons=body.persons, created_by=actor,
                     retention_until=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=config.DEFAULT_RETENTION_DAYS))
        db.add(row)
        if body.signal_id:
            db.add(CaseSignalDB(case_id=case_id, signal_id=body.signal_id, linked_by=actor))
        db.add(CaseTimelineDB(entry_id=str(uuid.uuid4()), case_id=case_id,
                              event_type="created", actor=actor, body="Case created"))
        record(db, actor=actor, action="case.created", resource_type="case", resource_id=case_id,
               data={"priority": body.priority, "signal_id": body.signal_id})
        db.flush()
        result = _case(row)
    notice = f"SEACOMMONS · NEW CASE\n{body.title}\nPriority: {body.priority}\nCase: {case_id[:8]}"
    telegram(notice)
    whatsapp(notice)
    return result


@router.get("/cases/{case_id}")
def get_case(case_id: str, request: Request) -> dict:
    with session_scope() as db:
        row = db.get(CaseDB, case_id)
        if row is None:
            raise HTTPException(404, "Case not found")
        _require_case_access(request, db, row)
        signals = db.execute(select(IngestedSignalDB).join(CaseSignalDB).where(CaseSignalDB.case_id == case_id)).scalars().all()
        timeline = db.execute(select(CaseTimelineDB).where(CaseTimelineDB.case_id == case_id).order_by(CaseTimelineDB.created_at.desc())).scalars().all()
        attachments = db.execute(select(CaseAttachmentDB).where(CaseAttachmentDB.case_id == case_id).order_by(CaseAttachmentDB.created_at.desc())).scalars().all()
        return {**_case(row), "signals": [s.payload for s in signals],
                "timeline": [{c.name: getattr(t, c.name) for c in t.__table__.columns} for t in timeline],
                "attachments": [{c.name: getattr(a, c.name) for c in a.__table__.columns if c.name != "object_key"} for a in attachments]}


@router.patch("/cases/{case_id}")
def update_case(case_id: str, body: CaseUpdate, request: Request) -> dict:
    changes = body.model_dump(exclude_none=True)
    if "status" in changes and changes["status"] not in STATUSES:
        raise HTTPException(422, "Invalid status")
    if "priority" in changes and changes["priority"] not in PRIORITIES:
        raise HTTPException(422, "Invalid priority")
    actor = _actor(request)
    with session_scope() as db:
        row = db.get(CaseDB, case_id)
        if row is None:
            raise HTTPException(404, "Case not found")
        _require_case_access(request, db, row, write=True)
        for field, value in changes.items():
            setattr(row, field, value)
        row.updated_at = datetime.now(timezone.utc)
        db.add(CaseTimelineDB(entry_id=str(uuid.uuid4()), case_id=case_id,
                              event_type="updated", actor=actor, body="Case updated", data=changes))
        record(db, actor=actor, action="case.updated", resource_type="case", resource_id=case_id, data=changes)
        db.flush()
        result = _case(row)
    if "status" in changes:
        notice = f"SEACOMMONS · CASE {case_id[:8]}\nStatus: {changes['status']}\n{result['title']}"
        telegram(notice)
        whatsapp(notice)
    return result


@router.post("/cases/{case_id}/signals/{signal_id}", status_code=201)
def link_signal(case_id: str, signal_id: str, request: Request) -> dict:
    with session_scope() as db:
        case = db.get(CaseDB, case_id)
        signal = db.get(IngestedSignalDB, signal_id)
        if case is None or signal is None:
            raise HTTPException(404, "Case or signal not found")
        _require_case_access(request, db, case, write=True)
        if signal.organization_id and signal.organization_id != case.organization_id:
            raise HTTPException(403, "Signal belongs to another organization")
        if db.get(CaseSignalDB, (case_id, signal_id)) is not None:
            return {"status": "already_linked"}
        actor = _actor(request)
        db.add(CaseSignalDB(case_id=case_id, signal_id=signal_id, linked_by=actor))
        record(db, actor=actor, action="case.signal_linked", resource_type="case", resource_id=case_id,
               data={"signal_id": signal_id})
        return {"status": "linked"}


@router.post("/cases/{case_id}/timeline", status_code=201)
def add_timeline(case_id: str, body: TimelineCreate, request: Request) -> dict:
    with session_scope() as db:
        case = db.get(CaseDB, case_id)
        if case is None:
            raise HTTPException(404, "Case not found")
        _require_case_access(request, db, case, write=True)
        actor = _actor(request)
        row = CaseTimelineDB(entry_id=str(uuid.uuid4()), case_id=case_id,
                             event_type=body.event_type, actor=actor, body=body.body, data=body.data)
        db.add(row)
        record(db, actor=actor, action="case.timeline_added", resource_type="case", resource_id=case_id,
               data={"event_type": body.event_type})
        db.flush()
        return {c.name: getattr(row, c.name) for c in row.__table__.columns}


_ALLOWED_TYPES = {"application/pdf", "text/plain", "text/csv", "application/json",
                  "image/jpeg", "image/png", "image/webp", "audio/mpeg", "audio/ogg", "audio/wav"}


@router.post("/cases/{case_id}/attachments", status_code=201)
async def upload_attachment(case_id: str, request: Request, file: UploadFile = File(...)) -> dict:
    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(415, "Unsupported attachment type")
    data = await file.read(config.MAX_ATTACHMENT_BYTES + 1)
    if len(data) > config.MAX_ATTACHMENT_BYTES:
        raise HTTPException(413, "Attachment too large")
    actor = _actor(request)
    attachment_id = str(uuid.uuid4())
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "attachment")[:180]
    key = f"cases/{case_id}/{attachment_id}/{safe_name}"
    digest = hashlib.sha256(data).hexdigest()
    with session_scope() as db:
        case = db.get(CaseDB, case_id)
        if case is None:
            raise HTTPException(404, "Case not found")
        _require_case_access(request, db, case, write=True)
    object_store.put(key, data, content_type)
    with session_scope() as db:
        row = CaseAttachmentDB(attachment_id=attachment_id, case_id=case_id, object_key=key,
                               filename=safe_name, content_type=content_type, size_bytes=len(data),
                               sha256=digest, uploaded_by=actor)
        db.add(row)
        db.add(CaseTimelineDB(entry_id=str(uuid.uuid4()), case_id=case_id, event_type="attachment",
                              actor=actor, body=f"Attachment added: {safe_name}", data={"attachment_id": attachment_id}))
        record(db, actor=actor, action="case.attachment_added", resource_type="case", resource_id=case_id,
               data={"attachment_id": attachment_id, "sha256": digest})
        db.flush()
        return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name != "object_key"}


@router.get("/cases/{case_id}/attachments/{attachment_id}")
def download_attachment(case_id: str, attachment_id: str, request: Request) -> Response:
    with session_scope() as db:
        case = db.get(CaseDB, case_id)
        if case is None: raise HTTPException(404, "Case not found")
        _require_case_access(request, db, case)
        row = db.get(CaseAttachmentDB, attachment_id)
        if row is None or row.case_id != case_id:
            raise HTTPException(404, "Attachment not found")
        key, filename, content_type = row.object_key, row.filename, row.content_type
    try:
        data = object_store.get(key)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Attachment object missing") from exc
    return Response(content=data, media_type=content_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff"})


@router.get("/audit")
def audit_log(resource_id: str | None = None, limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    with session_scope() as db:
        query = select(AuditLogDB)
        if resource_id:
            query = query.where(AuditLogDB.resource_id == resource_id)
        rows = db.execute(query.order_by(AuditLogDB.created_at.desc()).limit(limit)).scalars().all()
        return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in rows]
