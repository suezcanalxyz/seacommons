from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite:///./core/data/test_security.db")
os.environ.setdefault("RUNTIME_PROFILE", "operational")

from fastapi.testclient import TestClient

from core.api.main import app
from core.config import config
from core.db.models import IngestedSignalDB, OrganizationDB
from core.db.session import init_database, session_scope

init_database()
client = TestClient(app)


def test_partner_whatsapp_connector_and_signed_webhook() -> None:
    suffix = uuid.uuid4().hex[:10]
    organization_id = str(uuid.uuid4())
    phone_number_id = f"phone-{suffix}"
    with session_scope() as db:
        db.add(
            OrganizationDB(
                organization_id=organization_id,
                name=f"Connector partner {suffix}",
                slug=f"connector-{suffix}",
            )
        )

    previous = (
        config.META_APP_ID,
        config.META_APP_SECRET,
        config.META_WEBHOOK_VERIFY_TOKEN,
        config.META_EMBEDDED_SIGNUP_CONFIG_ID,
        config.PUBLIC_API_URL,
    )
    config.META_APP_ID = ""
    config.META_APP_SECRET = ""
    config.META_WEBHOOK_VERIFY_TOKEN = ""
    config.META_EMBEDDED_SIGNUP_CONFIG_ID = ""
    config.PUBLIC_API_URL = "https://api.seacommons.org"
    try:
        created = client.post(
            "/api/v1/connectors",
            json={
                "organization_id": organization_id,
                "display_name": "Partner operations",
                "external_account_id": f"waba-{suffix}",
                "external_channel_id": phone_number_id,
                "display_address": "+39000000000",
                "secret_ref": f"oracle/seacommons/connectors/{suffix}",
            },
        )
        assert created.status_code == 201, created.text
        connector = created.json()
        connector_id = connector["connector_id"]
        assert connector["status"] == "pending"
        assert connector["credentials_configured"] is True
        assert "secret_ref" not in connector

        onboarding = client.get("/api/v1/connectors/onboarding")
        assert onboarding.status_code == 200
        assert onboarding.json()["app_configured"] is False
        assert set(onboarding.json()).isdisjoint(
            {"app_secret", "webhook_verify_token", "access_token"}
        )

        refused = client.patch(
            f"/api/v1/connectors/{connector_id}", json={"status": "active"}
        )
        assert refused.status_code == 409

        config.META_APP_ID = "public-app-id"
        config.META_APP_SECRET = "test-app-secret"
        config.META_WEBHOOK_VERIFY_TOKEN = "test-verify-token"
        config.META_EMBEDDED_SIGNUP_CONFIG_ID = "public-config-id"
        activated = client.patch(
            f"/api/v1/connectors/{connector_id}", json={"status": "active"}
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["status"] == "active"

        challenge = client.get(
            "/api/v1/ingest/meta/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test-verify-token",
                "hub.challenge": "challenge-ok",
            },
        )
        assert challenge.status_code == 200
        assert challenge.text == "challenge-ok"

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": f"waba-{suffix}",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {"phone_number_id": phone_number_id},
                                "contacts": [
                                    {
                                        "wa_id": "393331234567",
                                        "profile": {"name": "Partner operator"},
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": "393331234567",
                                        "id": f"wamid.{suffix}",
                                        "timestamp": "1785196800",
                                        "type": "location",
                                        "location": {
                                            "latitude": 35.52,
                                            "longitude": 13.77,
                                            "name": "Position",
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
        body = json.dumps(payload, separators=(",", ":")).encode()
        signature = "sha256=" + hmac.new(
            config.META_APP_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        accepted = client.post(
            "/api/v1/ingest/meta/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["accepted"] == 1
        signal_id = accepted.json()["signal_ids"][0]
        with session_scope() as db:
            signal = db.get(IngestedSignalDB, signal_id)
            assert signal.organization_id == organization_id
            assert signal.connector_id == connector_id
            assert signal.payload["publication_status"] == "private"
            assert signal.payload["lat"] == 35.52
            assert signal.payload["lon"] == 13.77

        rejected = client.post(
            "/api/v1/ingest/meta/whatsapp",
            content=body,
            headers={"X-Hub-Signature-256": "sha256=wrong"},
        )
        assert rejected.status_code == 401
    finally:
        (
            config.META_APP_ID,
            config.META_APP_SECRET,
            config.META_WEBHOOK_VERIFY_TOKEN,
            config.META_EMBEDDED_SIGNUP_CONFIG_ID,
            config.PUBLIC_API_URL,
        ) = previous
