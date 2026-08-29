# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import uuid
import hashlib
import re
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.db.models import AuditLogDB, CaseAccessDB, CaseAttachmentDB, CaseDB, CaseIntelEventDB, CaseSignalDB, CaseTimelineDB, IngestedSignalDB, MembershipDB
from core.db.session import session_scope
from core.security import authenticate
from core.audit import record
from core.config import config
from core import object_store
from core.notifications import telegram, whatsapp
from core.cases.service import (
    CASE_TYPES,
    DEFAULT_CASE_TYPE,
    PRIORITIES,
    STATUSES,
    open_case,
)

router = APIRouter(prefix="/api/v1", tags=["cases"])


class CaseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=256)
    priority: str = "medium"
    case_type: str = DEFAULT_CASE_TYPE
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
    case_type: str | None = None
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


def _resolve_intel_events(event_ids: list[str]) -> list[dict]:
    """Compact view of the OSINT intel events linked to a case (in-memory first)."""
    if not event_ids:
        return []
    from core.db.models import IntelEventDB
    from core.intel.store import intel_store

    resolved: dict[str, dict] = {}
    for event_id in event_ids:
        event = intel_store.get(event_id)
        if event is not None:
            resolved[event_id] = {
                "id": event.id, "type": event.type, "severity": event.severity,
                "title": event.title, "lat": event.lat, "lon": event.lon,
                "timestamp_utc": event.timestamp_utc, "url": event.url,
                "maritime_domain": event.maritime_domain(),
                "metadata": event.metadata,
            }
    missing = [eid for eid in event_ids if eid not in resolved]
    if missing:
        with session_scope() as db:
            for row in db.query(IntelEventDB).filter(IntelEventDB.id.in_(missing)).all():
                meta = dict(row.meta or {})
                resolved[row.id] = {
                    "id": row.id, "type": row.type, "severity": row.severity,
                    "title": row.title, "lat": row.lat, "lon": row.lon,
                    "timestamp_utc": row.timestamp_utc, "url": row.url,
                    "maritime_domain": meta.get("maritime_domain") or "sar",
                    "metadata": meta,
                }
    return [resolved[eid] for eid in event_ids if eid in resolved]


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
def list_cases(
    request: Request,
    status: str | None = None,
    case_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    with session_scope() as db:
        query = select(CaseDB)
        if status:
            query = query.where(CaseDB.status == status)
        if case_type:
            query = query.where(CaseDB.case_type == case_type)
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
    if body.case_type not in CASE_TYPES:
        raise HTTPException(422, "Invalid case_type")
    actor = _actor(request)
    organization_id = body.organization_id or _principal_org(request)
    principal = authenticate(request)
    if config.AUTH_ENABLED:
        if not principal or ("administrator" not in principal.roles and organization_id != _principal_org(request)):
            raise HTTPException(403, "Invalid organization")
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
        return open_case(
            db,
            title=body.title,
            created_by=actor,
            case_type=body.case_type,
            priority=body.priority,
            sensitivity=body.sensitivity,
            summary=body.summary,
            lat=body.lat,
            lon=body.lon,
            persons=body.persons,
            organization_id=organization_id,
            signal_id=body.signal_id,
            audit_data={"priority": body.priority, "signal_id": body.signal_id},
        )


@router.get("/cases/{case_id}")
def get_case(case_id: str, request: Request) -> dict:
    with session_scope() as db:
        row = db.get(CaseDB, case_id)
        if row is None:
            raise HTTPException(404, "Case not found")
        _require_case_access(request, db, row)
        signals = db.execute(select(IngestedSignalDB).join(CaseSignalDB).where(CaseSignalDB.case_id == case_id)).scalars().all()
        intel_links = db.execute(select(CaseIntelEventDB).where(CaseIntelEventDB.case_id == case_id).order_by(CaseIntelEventDB.linked_at.desc())).scalars().all()
        intel_events = _resolve_intel_events([link.event_id for link in intel_links])
        timeline = db.execute(select(CaseTimelineDB).where(CaseTimelineDB.case_id == case_id).order_by(CaseTimelineDB.created_at.desc())).scalars().all()
        attachments = db.execute(select(CaseAttachmentDB).where(CaseAttachmentDB.case_id == case_id).order_by(CaseAttachmentDB.created_at.desc())).scalars().all()
        return {**_case(row), "signals": [s.payload for s in signals],
                "intel_events": intel_events,
                "timeline": [{c.name: getattr(t, c.name) for c in t.__table__.columns} for t in timeline],
                "attachments": [{c.name: getattr(a, c.name) for c in a.__table__.columns if c.name != "object_key"} for a in attachments]}


@router.get("/cases/{case_id}/dossier")
def case_dossier(case_id: str, request: Request) -> dict:
    """Evidence dossier — the full traceable signal chain behind the case."""
    with session_scope() as db:
        row = db.get(CaseDB, case_id)
        if row is None:
            raise HTTPException(404, "Case not found")
        _require_case_access(request, db, row)
    from core.cases.dossier import build_dossier

    dossier = build_dossier(case_id)
    if dossier is None:
        raise HTTPException(404, "Case not found")
    return dossier


@router.patch("/cases/{case_id}")
def update_case(case_id: str, body: CaseUpdate, request: Request) -> dict:
    changes = body.model_dump(exclude_none=True)
    if "status" in changes and changes["status"] not in STATUSES:
        raise HTTPException(422, "Invalid status")
    if "priority" in changes and changes["priority"] not in PRIORITIES:
        raise HTTPException(422, "Invalid priority")
    if "case_type" in changes and changes["case_type"] not in CASE_TYPES:
        raise HTTPException(422, "Invalid case_type")
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
