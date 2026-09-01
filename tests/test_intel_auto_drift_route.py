# SPDX-License-Identifier: AGPL-3.0-or-later
"""POST /api/v1/intel/auto-drift must reject maritime-security events.

docs/deep-research-report.md #17, hard requirement: SeaCommons Drift is a
humanitarian SAR model only. This is a public, unauthenticated endpoint
reachable from the anonymous Live map -- it must not let a caller spin up a
drift simulation for a sanctions/grey_zone/iuu_fishing/smuggling event just
by supplying that event's id.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from core.api.main import app
from core.intel.store import IntelEvent, intel_store

client = TestClient(app)


def test_auto_drift_rejects_maritime_security_event():
    event = IntelEvent(
        id="auto-drift-security-01",
        type="ais_anomaly",
        severity="high",
        lat=35.0,
        lon=14.0,
        title="AIS spoofing near sanctioned vessel",
        source="SeaCommons MDA",
        metadata={"anomaly_type": "sanctioned_vessel", "source_policy": "official_api"},
    )
    assert intel_store.add(event) is True
    try:
        resp = client.post(
            "/api/v1/intel/auto-drift",
            json={"intel_event_id": "auto-drift-security-01", "lat": 35.0, "lon": 14.0},
        )
        assert resp.status_code == 400
    finally:
        with intel_store._lock:
            intel_store._events = type(intel_store._events)(
                (e for e in intel_store._events if e.id != event.id),
                maxlen=intel_store._events.maxlen,
            )


def test_auto_drift_rejects_piracy_event():
    """docs/deep-research-report (2).md's follow-up finding: "not security"
    is not the same test as "is humanitarian". piracy is in the default
    public/humanitarian maritime-domain allow-list (domains_for_mode
    ("humanitarian") includes it), so the earlier fix (reject only
    SECURITY_MARITIME_DOMAINS) would still have let a piracy-domain event
    through. The positive HUMANITARIAN_DRIFT_DOMAINS gate must not."""
    event = IntelEvent(
        id="auto-drift-piracy-01",
        type="piracy_incident",
        severity="high",
        lat=35.0,
        lon=14.0,
        title="Boarding reported",
        source="SeaCommons MDA",
        metadata={"source_policy": "official_api"},
    )
    assert intel_store.add(event) is True
    try:
        resp = client.post(
            "/api/v1/intel/auto-drift",
            json={"intel_event_id": "auto-drift-piracy-01", "lat": 35.0, "lon": 14.0},
        )
        assert resp.status_code == 400
    finally:
        with intel_store._lock:
            intel_store._events = type(intel_store._events)(
                (e for e in intel_store._events if e.id != event.id),
                maxlen=intel_store._events.maxlen,
            )


def test_auto_drift_rejects_disputed_ocr_coordinate():
    """docs/fixes.md F-01: a coordinate flagged as a machine-OCR disagreement
    must never become a drift model origin, even for a humanitarian SAR event
    and even when the caller supplies a clean lat/lon in the request body."""
    event = IntelEvent(
        id="auto-drift-disputed-01",
        type="twitter",
        severity="high",
        lat=34.2,
        lon=12.0,
        title="Distress reported south of Crete",
        source="alarm_phone",
        metadata={
            "is_distress": True,
            "source_policy": "operator_published",
            "coordinate_source": "media_ocr_text",
            "coordinate_review_status": "machine_ocr_disputed_needs_review",
            "location_uncertainty_m": 3500,
        },
    )
    assert intel_store.add(event) is True
    try:
        resp = client.post(
            "/api/v1/intel/auto-drift",
            json={"intel_event_id": "auto-drift-disputed-01", "lat": 34.2, "lon": 12.0},
        )
        assert resp.status_code == 400
        assert "disputed" in resp.json()["detail"]
    finally:
        with intel_store._lock:
            intel_store._events = type(intel_store._events)(
                (e for e in intel_store._events if e.id != event.id),
                maxlen=intel_store._events.maxlen,
            )


def test_auto_drift_accepts_humanitarian_event(monkeypatch):
    event = IntelEvent(
        id="auto-drift-humanitarian-01",
        type="distress",
        severity="high",
        lat=35.0,
        lon=14.0,
        title="Distress report",
        source="alarm_phone",
        metadata={
            "is_distress": True,
            "source_policy": "official_api",
            # A coordinate parsed straight from the post text -- the canonical
            # drift-eligible location evidence (docs/fixes.md F-01).
            "coordinate_source": "post_text",
            "coordinate_review_status": "not_required",
        },
    )
    assert intel_store.add(event) is True
    monkeypatch.setattr("core.api.routes.intel.schedule_intel_drift", lambda *a, **k: True)
    try:
        resp = client.post(
            "/api/v1/intel/auto-drift",
            json={"intel_event_id": "auto-drift-humanitarian-01", "lat": 35.0, "lon": 14.0},
        )
        assert resp.status_code == 200
    finally:
        with intel_store._lock:
            intel_store._events = type(intel_store._events)(
                (e for e in intel_store._events if e.id != event.id),
                maxlen=intel_store._events.maxlen,
            )
