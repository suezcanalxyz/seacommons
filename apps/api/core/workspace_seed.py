"""Explicit operator import of repository templates into private workspace storage.

python -m core.workspace_seed --organization seacommons --deck /path/deck.md
Templates in a public repository are public. Store actual internal material only
in workspace_records through the authenticated UI or a private operator path.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from core.db.models import WorkspaceRecord, WorkspaceRevision
from core.db.session import session_scope


def import_document(organization: str, path: Path, *, kind: str, title: str) -> str:
    body = path.read_text(encoding="utf-8")
    if len(body) > 200_000:
        raise ValueError("Document exceeds workspace limit")
    now = datetime.now(timezone.utc).isoformat()
    with session_scope() as session:
        existing = session.scalar(select(WorkspaceRecord).where(
            WorkspaceRecord.organization_id == organization,
            WorkspaceRecord.title == title, WorkspaceRecord.kind == kind,
        ))
        if existing:
            return existing.id
        record_id = str(uuid4())
        row = WorkspaceRecord(id=record_id, organization_id=organization, kind=kind,
                              title=title, body=body, status="draft", owner="", version=1,
                              created_by="operator-import", updated_by="operator-import",
                              created_at=now, updated_at=now)
        session.add(row)
        session.flush()
        snapshot = {field: getattr(row, field) for field in
                    ("id", "kind", "title", "body", "status", "owner", "due_on", "version", "created_at", "updated_at")}
        session.add(WorkspaceRevision(id=str(uuid4()), record_id=record_id,
                                     organization_id=organization, version=1,
                                     actor="operator-import", timestamp=now, snapshot=snapshot))
        return record_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a deck into the private partner workspace")
    parser.add_argument("--organization", required=True)
    parser.add_argument("--deck", type=Path, required=True)
    parser.add_argument("--title", default="SeaCommons project deck")
    args = parser.parse_args()
    if not args.organization.strip() or len(args.organization) > 128:
        parser.error("Use a valid organisation identifier")
    print(import_document(args.organization, args.deck, kind="deck", title=args.title))


if __name__ == "__main__":
    main()
