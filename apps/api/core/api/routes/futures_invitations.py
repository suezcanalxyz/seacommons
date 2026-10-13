"""Futures invitations: identity-bound proposals, auditable reviews, no implicit account grants."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from core.config import config
from core.security import authenticate
from core.db.session import session_scope
from core.db.models import FuturesInvitationDB, FuturesInvitationReviewDB

router = APIRouter(prefix='/api/v1/futures/invitations', tags=['futures-invitations'])

class InvitationInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def identity(request: Request):
    # No local-development identity may create partner invites on an internet-facing API.
    if not config.AUTH_ENABLED:
        raise HTTPException(503, 'Partner invitations require configured OIDC authentication')
    principal = authenticate(request)
    if principal is None or not (principal.roles & {'administrator', 'manager', 'operator', 'member'}):
        raise HTTPException(403, 'Partner membership required')
    return principal


def serialize(row):
    return dict(id=row.id, first_name=row.first_name, last_name=row.last_name,
                email=row.email, status=row.status, proposed_by=row.proposed_by,
                created_at=row.created_at.isoformat() if row.created_at else None)

@router.post('', status_code=201)
def propose(body: InvitationInput, request: Request):
    principal = identity(request)
    email = str(body.email).strip().lower()
    with session_scope() as db:
        previous = db.execute(select(FuturesInvitationDB).where(FuturesInvitationDB.email == email,
            FuturesInvitationDB.status.in_(['pending','preapproved']))).scalar_one_or_none()
        if previous:
            raise HTTPException(409, 'An invitation for this email is already pending')
        row = FuturesInvitationDB(id=str(uuid.uuid4()), first_name=body.first_name.strip(),
            last_name=body.last_name.strip(), email=email, proposed_by=principal.subject, status='pending')
        db.add(row)
        db.flush()
        return serialize(row)

@router.get('')
def list_invitations(request: Request):
    principal = identity(request)
    with session_scope() as db:
        query = select(FuturesInvitationDB)
        if 'administrator' not in principal.roles:
            query = query.where(FuturesInvitationDB.proposed_by == principal.subject)
        rows = db.execute(query.order_by(FuturesInvitationDB.created_at.desc()).limit(100)).scalars().all()
        return [serialize(row) for row in rows]

@router.get('/reviews')
def reviews(request: Request):
    principal = identity(request)
    if 'administrator' not in principal.roles:
        raise HTTPException(403, 'Administrator required')
    with session_scope() as db:
        rows = db.execute(select(FuturesInvitationReviewDB).order_by(FuturesInvitationReviewDB.created_at.desc()).limit(30)).scalars().all()
        return [dict(created_at=x.created_at.isoformat(), pending=x.pending, preapproved=x.preapproved,
                     reviewed=x.reviewed, summary=x.summary) for x in rows]


def scheduled_review():
    """Summary and policy-based preapproval only. Never create a membership or send access links."""
    allowed = {v.strip().lower() for v in os.getenv('FUTURES_INVITE_APPROVED_EMAILS','').split(',') if v.strip()}
    with session_scope() as db:
        pending = db.execute(select(FuturesInvitationDB).where(FuturesInvitationDB.status == 'pending')).scalars().all()
        approved = 0
        for row in pending:
            if row.email in allowed:
                row.status = 'preapproved'
                row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                approved += 1
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        recent = db.execute(select(func.count()).select_from(FuturesInvitationDB).where(FuturesInvitationDB.created_at >= cutoff)).scalar_one()
        review = FuturesInvitationReviewDB(id=str(uuid.uuid4()), pending=len(pending)-approved,
            preapproved=approved, reviewed=recent,
            summary=f'{recent} invitation proposals in the last 24h; {approved} policy-preapproved; {len(pending)-approved} awaiting admin review. No account access granted.')
        db.add(review)
        return review.summary
