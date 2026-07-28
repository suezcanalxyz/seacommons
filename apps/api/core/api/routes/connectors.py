# SPDX-License-Identifier: AGPL-3.0-or-later
"""Partner connector onboarding and lifecycle management."""
from __future__ import annotations

import re
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.audit import record
from core.config import config
from core.connectors.service import public_connector
from core.db.models import ConnectorDB, MembershipDB, OrganizationDB
from core.db.session import session_scope
from core.security import Principal, authenticate

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])

_MANAGE_ROLES = {"administrator", "integration_service"}
_MEMBER_MANAGE_ROLES = {"manager", "data_steward"}
_SECRET_REF = re.compile(r"^[A-Za-z0-9_./:-]{3,256}$")


class ConnectorCreate(BaseModel):
    organization_id: str
    provider: Literal["whatsapp_cloud"] = "whatsapp_cloud"
    display_name: str = Field(min_length=2, max_length=128)
    external_account_id: str | None = Field(default=None, max_length=128)
    external_channel_id: str = Field(min_length=2, max_length=128)
    display_address: str | None = Field(default=None, max_length=128)
    secret_ref: str | None = Field(default=None, max_length=256)
    publication_policy: Literal["private", "internal"] = "private"


class ConnectorUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=128)
    display_address: str | None = Field(default=None, max_length=128)
    secret_ref: str | None = Field(default=None, max_length=256)
    publication_policy: Literal["private", "internal"] | None = None
    status: Literal["pending", "active", "paused"] | None = None


def _claim(claims: dict, path: str):
    value = claims
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _principal(request: Request) -> Principal:
    principal = authenticate(request)
    if principal is None:
        raise HTTPException(401, "Authentication required")
    return principal


def _can_manage(principal: Principal, db, organization_id: str) -> bool:
    if principal.roles & _MANAGE_ROLES:
        return True
    claim_org = _claim(principal.claims, config.OIDC_ORGANIZATION_CLAIM)
    if str(claim_org or "") != organization_id:
        return False
    membership = db.get(MembershipDB, (organization_id, principal.subject))
    return bool(membership and membership.role in _MEMBER_MANAGE_ROLES)


def _require_manage(principal: Principal, db, organization_id: str) -> None:
    if not _can_manage(principal, db, organization_id):
        raise HTTPException(403, "No connector-management access for this organization")


def _validate_secret_ref(value: str | None) -> None:
    if value and not _SECRET_REF.fullmatch(value):
        raise HTTPException(
            422,
            "secret_ref must be a secret-manager path, never a token or password",
        )


@router.get("/onboarding")
def onboarding(request: Request) -> dict:
    _principal(request)
    callback = (
        f"{config.PUBLIC_API_URL.rstrip('/')}/api/v1/ingest/meta/whatsapp"
        if config.PUBLIC_API_URL
        else None
    )
    return {
        "provider": "whatsapp_cloud",
        "app_configured": bool(
            config.META_APP_ID
            and config.META_APP_SECRET
            and config.META_WEBHOOK_VERIFY_TOKEN
        ),
        "embedded_signup_configured": bool(
            config.META_APP_ID and config.META_EMBEDDED_SIGNUP_CONFIG_ID
        ),
        "app_id": config.META_APP_ID or None,
        "configuration_id": config.META_EMBEDDED_SIGNUP_CONFIG_ID or None,
        "callback_url": callback,
        "required_server_secrets": [
            "META_APP_SECRET",
            "META_WEBHOOK_VERIFY_TOKEN",
        ],
        "credential_storage": "external_secret_manager",
    }


@router.get("/organizations")
def connector_organizations(request: Request) -> list[dict]:
    principal = _principal(request)
    with session_scope() as db:
        query = select(OrganizationDB)
        if "administrator" not in principal.roles:
            org_id = _claim(principal.claims, config.OIDC_ORGANIZATION_CLAIM)
            if not org_id:
                return []
            query = query.where(OrganizationDB.organization_id == str(org_id))
        rows = db.execute(query.order_by(OrganizationDB.name)).scalars().all()
        return [
            {
                "organization_id": row.organization_id,
                "name": row.name,
                "slug": row.slug,
            }
            for row in rows
        ]


@router.get("")
def list_connectors(request: Request) -> list[dict]:
    principal = _principal(request)
    with session_scope() as db:
        query = select(ConnectorDB)
        if "administrator" not in principal.roles:
            org_id = _claim(principal.claims, config.OIDC_ORGANIZATION_CLAIM)
            if not org_id:
                return []
            query = query.where(ConnectorDB.organization_id == str(org_id))
        rows = db.execute(query.order_by(ConnectorDB.created_at.desc())).scalars().all()
        return [public_connector(row) for row in rows]


@router.post("", status_code=201)
def create_connector(body: ConnectorCreate, request: Request) -> dict:
    principal = _principal(request)
    _validate_secret_ref(body.secret_ref)
    row = ConnectorDB(
        connector_id=str(uuid.uuid4()),
        organization_id=body.organization_id,
        provider=body.provider,
        display_name=body.display_name,
        status="pending",
        external_account_id=body.external_account_id,
        external_channel_id=body.external_channel_id,
        display_address=body.display_address,
        secret_ref=body.secret_ref,
        publication_policy=body.publication_policy,
        created_by=principal.subject,
    )
    try:
        with session_scope() as db:
            if db.get(OrganizationDB, body.organization_id) is None:
                raise HTTPException(404, "Organization not found")
            _require_manage(principal, db, body.organization_id)
            db.add(row)
            record(
                db,
                actor=principal.subject,
                action="connector.created",
                resource_type="connector",
                resource_id=row.connector_id,
                data={"provider": row.provider, "organization_id": row.organization_id},
            )
            db.flush()
            return public_connector(row)
    except IntegrityError as exc:
        raise HTTPException(409, "This provider channel is already connected") from exc


@router.patch("/{connector_id}")
def update_connector(
    connector_id: str, body: ConnectorUpdate, request: Request
) -> dict:
    principal = _principal(request)
    changes = body.model_dump(exclude_unset=True)
    if "secret_ref" in changes:
        _validate_secret_ref(changes["secret_ref"])
    with session_scope() as db:
        row = db.get(ConnectorDB, connector_id)
        if row is None:
            raise HTTPException(404, "Connector not found")
        _require_manage(principal, db, row.organization_id)
        future_secret_ref = changes.get("secret_ref", row.secret_ref)
        if changes.get("status") == "active":
            if not (
                config.META_APP_ID
                and config.META_APP_SECRET
                and config.META_WEBHOOK_VERIFY_TOKEN
            ):
                raise HTTPException(409, "Meta application is not configured")
            if not future_secret_ref:
                raise HTTPException(409, "Partner credential secret reference is missing")
        for field, value in changes.items():
            setattr(row, field, value)
        record(
            db,
            actor=principal.subject,
            action="connector.updated",
            resource_type="connector",
            resource_id=row.connector_id,
            data={key: value for key, value in changes.items() if key != "secret_ref"},
        )
        db.flush()
        return public_connector(row)
