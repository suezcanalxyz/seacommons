# SPDX-License-Identifier: AGPL-3.0-or-later
"""Case creation as a reusable service.

The HTTP route (`core.api.routes.cases.create_case`) and the OSINT fusion
engine (`core.intel.fusion`) both need to open a case with the same side
effects — timeline entry, audit record, optional signal / intel-event links,
operator notification. That logic lives here once; the route validates the
request and delegates, the engine calls in directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from core.audit import record
from core.config import config
from core.db.models import (
    CaseDB,
    CaseIntelEventDB,
    CaseSignalDB,
    CaseTimelineDB,
)
from core.notifications import telegram, whatsapp

STATUSES = {"open", "triage", "active", "monitoring", "resolved", "closed"}
PRIORITIES = {"low", "medium", "high", "critical"}
SENSITIVITIES = {"public", "restricted", "confidential", "secret"}
# Coarse operational taxonomy so cases can be separated by the kind of event
# they track, independently of their lifecycle status. "unspecified" exists
# for cases created before the operator has classified them.
CASE_TYPES = {
    "distress_sar",
    "pushback",
    "shipwreck",
    "missing_persons",
    "interception",
    "vessel_incident",
    "monitoring",
    "unspecified",
    # Broader maritime-domain compartments (operator-only unless published).
    "sanctions_watch",
    "dark_rendezvous",
    "subsea_infrastructure",
    "piracy_incident",
}
DEFAULT_CASE_TYPE = "distress_sar"

OPEN_STATUSES = {"open", "triage", "active", "monitoring"}


def case_to_dict(row: CaseDB) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def open_case(
    db,
    *,
    title: str,
    created_by: str,
    case_type: str = DEFAULT_CASE_TYPE,
    priority: str = "medium",
    sensitivity: str = "restricted",
    summary: str = "",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    persons: Optional[float] = None,
    organization_id: Optional[str] = None,
    signal_id: Optional[str] = None,
    intel_event_ids: Optional[Iterable[str]] = None,
    timeline_note: str = "Case created",
    audit_action: str = "case.created",
    audit_data: Optional[dict] = None,
    notify: bool = True,
) -> dict:
    """Create a case row + timeline + audit + links inside an open session.

    Caller owns the transaction (``db``); this flushes but does not commit.
    Returns the case as a plain dict. Notification is best-effort and fired
    after flush.
    """
    if case_type not in CASE_TYPES:
        case_type = DEFAULT_CASE_TYPE
    if priority not in PRIORITIES:
        priority = "medium"
    case_id = str(uuid.uuid4())
    row = CaseDB(
        case_id=case_id,
        organization_id=organization_id,
        title=title,
        priority=priority,
        case_type=case_type,
        sensitivity=sensitivity,
        summary=summary,
        lat=lat,
        lon=lon,
        persons=persons,
        created_by=created_by,
        retention_until=datetime.now(timezone.utc).replace(tzinfo=None)
        + timedelta(days=config.DEFAULT_RETENTION_DAYS),
    )
    db.add(row)
    if signal_id:
        db.add(CaseSignalDB(case_id=case_id, signal_id=signal_id, linked_by=created_by))
    for event_id in dict.fromkeys(intel_event_ids or []):
        db.add(
            CaseIntelEventDB(
                case_id=case_id,
                event_id=str(event_id),
                role="contributing",
                linked_by=created_by,
            )
        )
    db.add(
        CaseTimelineDB(
            entry_id=str(uuid.uuid4()),
            case_id=case_id,
            event_type="created",
            actor=created_by,
            body=timeline_note,
        )
    )
    record(
        db,
        actor=created_by,
        action=audit_action,
        resource_type="case",
        resource_id=case_id,
        data=audit_data or {"priority": priority, "case_type": case_type},
    )
    db.flush()
    result = case_to_dict(row)

    if notify:
        notice = (
            f"SEACOMMONS · NEW CASE\n{title}\n"
            f"Type: {case_type}  Priority: {priority}\nCase: {case_id[:8]}"
        )
        telegram(notice)
        whatsapp(notice)
    return result
