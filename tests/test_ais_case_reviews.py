from __future__ import annotations

import os
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "sqlite:///./core/data/test_ais_case_reviews.db")

from fastapi.testclient import TestClient
from core.api.main import app
from core.api.routes import operator_ais_review as module
from core.db.models import AISCaseReviewDB
from core.db.session import engine, session_scope
from core.security import Principal

client = TestClient(app)
CASE_ID = "episode:subj:imo:9316359:gap_episode:1"


def _feature():
    return {
        "type": "Feature",
        "id": CASE_ID,
        "geometry": {"type": "Point", "coordinates": [-1.15086, 37.16512]},
        "properties": {
            "id": CASE_ID,
            "title": "AIS reporting gap - MSC SPRING III",
            "linked_mmsi": "636017239",
            "imo": "9316359",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "anomaly_type": "long_gap",
            "verification_status": "single_source_observed",
            "resolution_state": "open",
        },
    }


def _auth(monkeypatch):
    monkeypatch.setenv("SEACOMMONS_AIS_REVIEWER_EMAILS", "reviewer@example.org")
    monkeypatch.setattr(module, "require_futures_identity",
        lambda _request: Principal("sub:reviewer-test", frozenset({"futures_viewer"}), {
            "email": "reviewer@example.org", "email_verified": True,
        }))
    monkeypatch.setattr(module, "public_signal_collection",
        lambda **_kwargs: {"features": [_feature()]})
    AISCaseReviewDB.__table__.create(bind=engine(), checkfirst=True)


def _payload():
    return {
        "case_id": CASE_ID,
        "verdict": "false_positive",
        "position_check": "consistent",
        "explanation": "The vessel reappeared after the reported gap and coverage boundaries explain the silence.",
        "external_visual_reference_checked": True,
    }


def test_reviews_are_append_only_snapshots_and_not_new_ais_evidence(monkeypatch):
    _auth(monkeypatch)
    before = client.get("/api/v1/operator/ais-reviews", params={"case_id": CASE_ID})
    assert before.status_code == 200
    count = before.json()["count"]

    response = client.post("/api/v1/operator/ais-reviews", json=_payload())
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["review_stage"] == "human_annotation_not_training"
    assert doc["case_snapshot"]["mmsi"] == "636017239"
    assert doc["case_snapshot"]["event_position"] == [-1.15086, 37.16512]
    assert doc["verdict"] == "false_positive"
    after = client.get("/api/v1/operator/ais-reviews", params={"case_id": CASE_ID})
    assert after.status_code == 200
    assert after.json()["count"] == count + 1
    with session_scope() as db:
        assert db.get(AISCaseReviewDB, doc["review_id"]).reviewer_sub == "sub:reviewer-test"
        db.query(AISCaseReviewDB).filter(AISCaseReviewDB.review_id == doc["review_id"]).delete()


def test_reviewer_identity_and_allowlist_fail_closed(monkeypatch):
    _auth(monkeypatch)
    monkeypatch.delenv("SEACOMMONS_AIS_REVIEWER_EMAILS")
    denied = client.post("/api/v1/operator/ais-reviews", json=_payload())
    assert denied.status_code == 503
    assert client.get("/api/v1/operator/ais-reviews", params={"case_id": CASE_ID}).status_code == 503
    monkeypatch.setenv("SEACOMMONS_AIS_REVIEWER_EMAILS", "another@example.org")
    assert client.post("/api/v1/operator/ais-reviews", json=_payload()).status_code == 403


def test_forged_case_or_unsupported_label_never_persists(monkeypatch):
    _auth(monkeypatch)
    forged = _payload()
    forged["case_id"] = "episode:forged:123456"
    assert client.post("/api/v1/operator/ais-reviews", json=forged).status_code == 409
    invalid = _payload()
    invalid["verdict"] = "training_override"
    assert client.post("/api/v1/operator/ais-reviews", json=invalid).status_code == 422
    missing_reason = _payload()
    missing_reason["explanation"] = "fake"
    assert client.post("/api/v1/operator/ais-reviews", json=missing_reason).status_code == 422
