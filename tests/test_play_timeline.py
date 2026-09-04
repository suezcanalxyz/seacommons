from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from core.api.main import app
from core.intel.humanitarian_incident import sync_incident_for_event
from core.intel.store import IntelEvent


@pytest.fixture(autouse=True)
def _fresh_play_tables():
    from core.db.models import DriftResultDB, HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import engine, session_scope

    for table in (HumanitarianIncidentDB, IncidentTransitionDB, DriftResultDB):
        table.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(HumanitarianIncidentDB).delete()
        db.query(IncidentTransitionDB).delete()
        db.query(DriftResultDB).delete()
    yield


def _seed_case(*, lifecycle="resolved", age_hours=30, with_update=True):
    from core.db.models import DriftResultDB, IntelEventDB
    from core.db.session import session_scope

    event_id = f"play-{uuid.uuid4()}"
    reported = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    update_at = reported + timedelta(hours=26)
    thread = []
    if with_update:
        thread = [{
            "tweet_id": f"reply-{event_id}",
            "posted_at": update_at.isoformat(),
            "url": f"https://example.test/{event_id}/reply",
            "kind": "reply",
            "note": "We are still waiting for news about the people.",
        }]
    event = IntelEvent(
        id=event_id, type="distress", severity="high", lat=35.4, lon=14.2,
        title="Public humanitarian report", text="PRIVATE RAW MESSAGE MUST NOT LEAK",
        source="Alarm Phone", timestamp_utc=reported.isoformat(),
        url=f"https://example.test/{event_id}",
        metadata={
            "is_distress": True,
            "maritime_domain": "sar",
            "source_policy": "operator_published",
            "publication_status": "published",
            "thread_reposts": thread,
        },
    )
    with session_scope() as db:
        db.add(IntelEventDB(
            id=event.id, timestamp_utc=event.timestamp_utc, type=event.type,
            severity=event.severity, lat=event.lat, lon=event.lon,
            title=event.title, text=event.text, url=event.url, source=event.source,
            linked_mmsi="", maritime_domain="sar", meta=event.metadata,
        ))
    sync_incident_for_event(event, lifecycle=lifecycle)
    with session_scope() as db:
        db.add(DriftResultDB(
            drift_id=f"drift-{uuid.uuid4()}", event_id=f"intel:{event_id}",
            domain="ocean_sar", lat=event.lat, lon=event.lon, status="completed",
            trajectory={"type": "LineString", "coordinates": [[14.2, 35.4], [14.3, 35.5]]},
            metadata_json={"model": "OpenDrift"}, created_at=reported.replace(tzinfo=None) + timedelta(minutes=10),
        ))
    return event_id


def test_play_incident_index_exposes_real_status_not_archived_label():
    event_id = _seed_case(lifecycle="resolved")
    response = TestClient(app).get("/api/v1/play/incidents?limit=50")
    assert response.status_code == 200
    incident = next(item for item in response.json()["incidents"] if item["incident_id"] == event_id)
    assert incident["incident_status"] == "resolved"
    assert incident["surface"] == "play"
    assert incident["incident_status"] != "archived"


def test_play_timeline_orders_report_drift_and_late_attending_news():
    event_id = _seed_case(lifecycle="needs_review", age_hours=40, with_update=True)
    response = TestClient(app).get(f"/api/v1/play/incidents/{event_id}/timeline")
    assert response.status_code == 200
    payload = response.json()
    assert payload["incident_status"] == "needs_review"
    items = payload["timeline"]
    assert [item["at"] for item in items] == sorted(item["at"] for item in items)
    types = [item["type"] for item in items]
    assert "report" in types
    assert "drift" in types
    assert "attending_news" in types


def test_play_timeline_never_exposes_raw_private_event_text():
    event_id = _seed_case(lifecycle="resolved")
    response = TestClient(app).get(f"/api/v1/play/incidents/{event_id}/timeline")
    assert response.status_code == 200
    body = response.text
    assert "PRIVATE RAW MESSAGE MUST NOT LEAK" not in body


def test_recent_active_incident_stays_out_of_play_index():
    event_id = _seed_case(lifecycle="active", age_hours=2, with_update=False)
    response = TestClient(app).get("/api/v1/play/incidents?limit=50")
    assert response.status_code == 200
    ids = {item["incident_id"] for item in response.json()["incidents"]}
    assert event_id not in ids
