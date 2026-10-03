from __future__ import annotations

import time

import jwt
import pytest
from core.api.routes import workspace
from core.config import config
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import partner_security

_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC = jwt.algorithms.ECAlgorithm.to_jwk(_KEY.public_key(), as_dict=True)
_PUBLIC.update(kid="test-partner-key", alg="ES256")
_ISSUER = "https://partner-test.supabase.co/auth/v1"
_APP = FastAPI()
_APP.include_router(workspace.router)
client = TestClient(_APP)


@pytest.fixture(autouse=True)
def configured_partner(monkeypatch):
    monkeypatch.setattr(config, "PARTNER_AUTH_ENABLED", True)
    monkeypatch.setattr(config, "PARTNER_AUTH_ISSUER", _ISSUER)
    monkeypatch.setattr(config, "PARTNER_AUTH_AUDIENCE", "authenticated")
    monkeypatch.setattr(config, "AUTH_ENABLED", False)
    monkeypatch.setattr(config, "PARTNER_ACCOUNTS", {
        "editor@example.org": {"subject": "editor-id", "organization_id": "sea", "role": "editor"},
        "viewer@example.org": {"subject": "viewer-id", "organization_id": "sea", "role": "viewer"},
        "other@example.org": {"subject": "other-id", "organization_id": "other", "role": "editor"},
    })
    monkeypatch.setattr(partner_security, "_partner_jwks", lambda force=False: {"keys": [_PUBLIC]})


def headers(email="editor@example.org", subject="editor-id", **extra):
    now = int(time.time())
    token = jwt.encode({"sub": subject, "email": email, "iss": _ISSUER,
                        "aud": "authenticated", "iat": now, "exp": now + 600, **extra},
                       _KEY, algorithm="ES256", headers={"kid": "test-partner-key"})
    return {"Authorization": f"Bearer {token}"}


def create_record(**values):
    return client.post("/api/v1/workspace/records", headers=headers(), json={
        "kind": "document", "title": "Private working notes", "body": "Confidential draft", **values,
    })


def test_workspace_has_no_development_auth_bypass(monkeypatch):
    assert client.get("/api/v1/workspace/me").status_code == 401
    monkeypatch.setattr(config, "PARTNER_AUTH_ENABLED", False)
    assert client.get("/api/v1/workspace/me", headers=headers()).status_code == 503


@pytest.mark.parametrize("claims", [
    {"email": "uninvited@example.org", "subject": "uninvited"},
    {"email": "editor@example.org", "subject": "reassigned-email"},
    {"is_anonymous": True}, {"exp": 0}, {"iss": "https://attacker.example/auth/v1"},
    {"aud": "wrong-audience"},
])
def test_invalid_or_unapproved_identities_are_denied(claims):
    assert client.get("/api/v1/workspace/me", headers=headers(**claims)).status_code in {401, 403}


def test_invalid_signature_cannot_open_workspace():
    forged = jwt.encode({"sub": "editor-id", "email": "editor@example.org", "iss": _ISSUER,
                         "aud": "authenticated", "iat": int(time.time()), "exp": int(time.time()) + 600},
                        ec.generate_private_key(ec.SECP256R1()), algorithm="ES256", headers={"kid": "test-partner-key"})
    assert client.get("/api/v1/workspace/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_user_metadata_cannot_escalate_workspace_permissions():
    viewer = headers("viewer@example.org", "viewer-id", user_metadata={"role": "administrator"}, roles=["administrator"])
    me = client.get("/api/v1/workspace/me", headers=viewer)
    assert me.json()["role"] == "viewer"
    assert me.json()["can_edit"] is False
    assert client.post("/api/v1/workspace/records", headers=viewer, json={"kind": "document", "title": "Denied"}).status_code == 403


def test_organisation_isolation_applies_to_content_edits_and_history():
    created = create_record()
    assert created.status_code == 201
    record_id = created.json()["id"]
    other = headers("other@example.org", "other-id")
    assert client.get("/api/v1/workspace/records", headers=other).json()["items"] == []
    assert client.get(f"/api/v1/workspace/records/{record_id}", headers=other).status_code == 404
    assert client.get(f"/api/v1/workspace/records/{record_id}/history", headers=other).status_code == 404
    assert client.put(f"/api/v1/workspace/records/{record_id}", headers=other, json={
        "kind": "document", "title": "Taken over", "version": 1,
    }).status_code == 404
    own = client.get(f"/api/v1/workspace/records/{record_id}", headers=headers())
    assert own.json()["body"] == "Confidential draft"
    assert own.headers["cache-control"] == "private, no-store"
    listed = client.get("/api/v1/workspace/records", headers=headers()).json()["items"]
    assert "body" not in listed[0]


def test_edits_keep_history_and_reject_stale_versions():
    record_id = create_record(kind="milestone", due_on="2026-11-01").json()["id"]
    changes = {"kind": "milestone", "title": "Validation", "body": "Reviewed", "status": "complete", "version": 1}
    assert client.put(f"/api/v1/workspace/records/{record_id}", headers=headers(), json=changes).status_code == 200
    assert client.put(f"/api/v1/workspace/records/{record_id}", headers=headers(), json=changes).status_code == 409
    history = client.get(f"/api/v1/workspace/records/{record_id}/history", headers=headers()).json()["items"]
    assert [entry["version"] for entry in history] == [2, 1]
    assert history[0]["snapshot"]["body"] == "Reviewed"


def test_empty_titles_and_invalid_dates_are_rejected():
    assert create_record(title="   ").status_code == 422
    assert create_record(due_on="tomorrow").status_code == 422


def test_full_api_uses_partner_auth_instead_of_development_or_operator_auth(monkeypatch):
    from core.api.main import app

    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "INTERNAL_PROXY_SECRET", "internal-operator-secret")
    monkeypatch.setattr(config, "DEMO_PUBLIC_MODE", False)
    full_client = TestClient(app)
    assert full_client.get("/api/v1/workspace/me").status_code == 401
    assert full_client.get("/api/v1/workspace/me", headers=headers()).status_code == 200
    created = full_client.post("/api/v1/workspace/records", headers=headers(), json={
        "kind": "analysis", "title": "Working assessment",
    })
    assert created.status_code == 201
    assert created.headers["cache-control"] == "private, no-store"
    assert full_client.post("/api/v1/cases", headers=headers(), json={"title": "Blocked"}).status_code == 401
