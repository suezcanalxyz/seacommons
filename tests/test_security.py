from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./core/data/test_security.db")
os.environ.setdefault("RUNTIME_PROFILE", "operational")

from fastapi.testclient import TestClient

from core.api.main import app
from core.config import config
from core.security import validate_production_security


client = TestClient(app)


def test_mutation_requires_auth_when_enabled() -> None:
    previous = config.AUTH_ENABLED
    config.AUTH_ENABLED = True
    try:
        response = client.post("/api/v1/alert", json={})
        assert response.status_code == 401
    finally:
        config.AUTH_ENABLED = previous


def test_production_fails_closed_without_oidc() -> None:
    values = config.RUNTIME_PROFILE, config.AUTH_ENABLED, config.OIDC_ISSUER
    config.RUNTIME_PROFILE = "production"
    config.AUTH_ENABLED = False
    config.OIDC_ISSUER = ""
    try:
        try:
            validate_production_security()
        except RuntimeError as exc:
            assert "Unsafe production configuration" in str(exc)
        else:
            raise AssertionError("production security validation did not fail")
    finally:
        config.RUNTIME_PROFILE, config.AUTH_ENABLED, config.OIDC_ISSUER = values


def test_telegram_rejects_wrong_secret() -> None:
    previous = config.TELEGRAM_WEBHOOK_SECRET
    config.TELEGRAM_WEBHOOK_SECRET = "correct-secret"
    try:
        response = client.post(
            "/api/v1/ingest/telegram",
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
            json={"update_id": 1},
        )
        assert response.status_code == 401
    finally:
        config.TELEGRAM_WEBHOOK_SECRET = previous


def test_case_lifecycle() -> None:
    created = client.post("/api/v1/cases", json={
        "title": "Test distress case", "priority": "high", "lat": 35.1, "lon": 15.4
    })
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    fetched = client.get(f"/api/v1/cases/{case_id}")
    assert fetched.status_code == 200
    assert fetched.json()["timeline"][0]["event_type"] == "created"
    updated = client.patch(f"/api/v1/cases/{case_id}", json={"status": "active"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "active"
    note = client.post(f"/api/v1/cases/{case_id}/timeline", json={"body": "Operator review completed"})
    assert note.status_code == 201
    upload = client.post(f"/api/v1/cases/{case_id}/attachments", files={"file": ("brief.txt", b"verified note", "text/plain")})
    assert upload.status_code == 201
    attachment = upload.json()
    assert len(attachment["sha256"]) == 64
    download = client.get(f"/api/v1/cases/{case_id}/attachments/{attachment['attachment_id']}")
    assert download.content == b"verified note"
    audit = client.get(f"/api/v1/audit?resource_id={case_id}")
    assert audit.status_code == 200
    assert {row["action"] for row in audit.json()} >= {"case.created", "case.updated", "case.attachment_added"}
    old_secret, old_chat = config.TELEGRAM_WEBHOOK_SECRET, config.TELEGRAM_OPERATIONS_CHAT_ID
    config.TELEGRAM_WEBHOOK_SECRET, config.TELEGRAM_OPERATIONS_CHAT_ID = "webhook-secret", "-100123"
    try:
        command = client.post("/api/v1/ingest/telegram",
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
            json={"update_id": 99, "message": {"chat": {"id": -100123}, "text": f"/case {case_id[:8]} Verified from bridge"}})
        assert command.status_code == 200
        assert command.json()["action"] == "case.telegram_note"
    finally:
        config.TELEGRAM_WEBHOOK_SECRET, config.TELEGRAM_OPERATIONS_CHAT_ID = old_secret, old_chat


def test_durable_job_queue_lifecycle() -> None:
    from core.jobs import claim, complete, enqueue, get
    job_id = enqueue("test", {"value": 1})
    claimed = claim("pytest-worker")
    assert claimed is not None and claimed["job_id"] == job_id
    assert claimed["attempts"] == 1
    complete(job_id, {"ok": True})
    stored = get(job_id)
    assert stored["status"] == "completed"
    assert stored["result"] == {"ok": True}
    previous_attempts = config.JOB_MAX_ATTEMPTS
    config.JOB_MAX_ATTEMPTS = 1
    try:
        dead_id = enqueue("test", {"fail": True})
        dead_job = claim("pytest-worker")
        assert dead_job["job_id"] == dead_id
        from core.jobs import fail
        assert fail(dead_id, "expected failure") == "dead"
        retried = client.post(f"/api/v1/jobs/{dead_id}/retry")
        assert retried.status_code == 200
        assert retried.json()["status"] == "queued"
        complete(dead_id, {"test_cleanup": True})
    finally:
        config.JOB_MAX_ATTEMPTS = previous_attempts


def test_drift_endpoint_can_enqueue() -> None:
    previous = config.JOB_EXECUTION_MODE
    config.JOB_EXECUTION_MODE = "queue"
    try:
        response = client.post("/api/v1/drift", json={"lat": 35.1, "lon": 15.4, "duration_h": 6})
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        assert job_id
        job = client.get(f"/api/v1/jobs/{job_id}")
        assert job.status_code == 200
        assert job.json()["status"] == "queued"
        from core.jobs import complete
        complete(job_id, {"test_cleanup": True})
    finally:
        config.JOB_EXECUTION_MODE = previous


def test_readiness_metrics_and_request_id() -> None:
    ready = client.get("/ready", headers={"X-Request-Id": "test-request-id"})
    assert ready.status_code == 200
    assert ready.headers["X-Request-Id"] == "test-request-id"
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "seacommons_http_requests_total" in metrics.text
    assert "seacommons_jobs" in metrics.text


def test_worker_heartbeat_admin_view() -> None:
    from core.jobs import heartbeat
    heartbeat("pytest:123", "pytest-host", 123)
    workers = client.get("/api/v1/admin/workers")
    assert workers.status_code == 200
    row = next(item for item in workers.json() if item["worker_id"] == "pytest:123")
    assert row["alive"] is True


def test_public_demo_allows_simulation_but_blocks_operational_mutations() -> None:
    previous_demo, previous_queue = config.DEMO_PUBLIC_MODE, config.JOB_EXECUTION_MODE
    config.DEMO_PUBLIC_MODE, config.JOB_EXECUTION_MODE = True, "queue"
    try:
        blocked = client.post("/api/v1/ingest/webhook", json={"text": "must not enter demo"})
        assert blocked.status_code == 403
        blocked_case = client.post("/api/v1/cases", json={"title": "must not be created"})
        assert blocked_case.status_code == 403
        simulation = client.post("/api/v1/alert", json={
            "lat": 35.1, "lon": 15.4, "timestamp": "2026-07-15T10:00:00Z",
            "persons": 12, "vessel_type": "rubber_boat", "domain": "ocean_sar",
        })
        assert simulation.status_code == 200
        from core.jobs import complete
        complete(simulation.json()["event_id"], {"test_cleanup": True})
    finally:
        config.DEMO_PUBLIC_MODE, config.JOB_EXECUTION_MODE = previous_demo, previous_queue


def test_whatsapp_notification_uses_configured_twilio_channel(monkeypatch) -> None:
    from core import notifications
    previous = (
        config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN,
        config.TWILIO_WHATSAPP_NUMBER, config.TWILIO_OPERATIONS_WHATSAPP_TO,
    )
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr(notifications.httpx, "post", fake_post)
    config.TWILIO_ACCOUNT_SID = "AC123"
    config.TWILIO_AUTH_TOKEN = "token"
    config.TWILIO_WHATSAPP_NUMBER = "+390001"
    config.TWILIO_OPERATIONS_WHATSAPP_TO = "+390002"
    try:
        assert notifications.whatsapp("Research case update") is True
        assert captured["url"].endswith("/Accounts/AC123/Messages.json")
        assert captured["data"]["From"] == "whatsapp:+390001"
        assert captured["data"]["To"] == "whatsapp:+390002"
    finally:
        (
            config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN,
            config.TWILIO_WHATSAPP_NUMBER, config.TWILIO_OPERATIONS_WHATSAPP_TO,
        ) = previous


def test_public_demo_drift_has_explicit_degraded_fallback(monkeypatch) -> None:
    from datetime import datetime, timezone
    from core.drift import engine as engine_module

    drift = engine_module.DriftEngine()
    monkeypatch.setattr(drift._cache, "get_wind_live", lambda *_: {"wind_speed_ms": 5.0, "wind_dir_deg": 270.0})
    monkeypatch.setattr(drift._cache, "get_ocean_currents", lambda *_: {"u_ms": 0.1, "v_ms": 0.02})
    monkeypatch.setattr(drift._cache, "get_wind_forecast_series", lambda *_, **__: [])
    monkeypatch.setattr(engine_module, "run_leeway", lambda *_: (_ for _ in ()).throw(RuntimeError("OpenDrift unavailable")))
    previous = config.DEMO_PUBLIC_MODE
    config.DEMO_PUBLIC_MODE = True
    try:
        result = drift.compute(35.9, 14.5, datetime.now(timezone.utc), duration_h=24)
        assert result.metadata["model"] == "degraded demonstration fallback"
        assert result.metadata["operational_use"] is False
        assert result.cone_24h["geometry"]["type"] == "Polygon"
    finally:
        config.DEMO_PUBLIC_MODE = previous
