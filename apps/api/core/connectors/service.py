# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from core.db.models import ConnectorDB


def public_connector(row: ConnectorDB) -> dict[str, Any]:
    """Serialize a connector without exposing its secret-manager reference."""
    return {
        "connector_id": row.connector_id,
        "organization_id": row.organization_id,
        "provider": row.provider,
        "display_name": row.display_name,
        "status": row.status,
        "external_account_id": row.external_account_id,
        "external_channel_id": row.external_channel_id,
        "display_address": row.display_address,
        "credentials_configured": bool(row.secret_ref),
        "publication_policy": row.publication_policy,
        "configuration": row.configuration or {},
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "last_seen_at": row.last_seen_at,
    }


def active_whatsapp_connector(db, phone_number_id: str) -> ConnectorDB | None:
    return db.execute(
        select(ConnectorDB).where(
            ConnectorDB.provider == "whatsapp_cloud",
            ConnectorDB.external_channel_id == phone_number_id,
            ConnectorDB.status == "active",
        )
    ).scalar_one_or_none()


def mark_seen(row: ConnectorDB) -> None:
    row.last_seen_at = datetime.now(timezone.utc)


def status_counts(db, provider: str | None = None) -> dict[str, int]:
    query = select(ConnectorDB)
    if provider:
        query = query.where(ConnectorDB.provider == provider)
    result: dict[str, int] = {}
    for row in db.execute(query).scalars():
        result[row.status] = result.get(row.status, 0) + 1
    return result

