from __future__ import annotations
import uuid
from sqlalchemy.orm import Session
from core.db.models import AuditLogDB


def record(db: Session, *, actor: str, action: str, resource_type: str, resource_id: str, data: dict | None = None) -> None:
    db.add(AuditLogDB(audit_id=str(uuid.uuid4()), actor=actor, action=action,
                      resource_type=resource_type, resource_id=resource_id, data=data or {}))
