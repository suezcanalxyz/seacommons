# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression for canonical Live marker/drift status parity (issue #367)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.intel.store import IntelEvent


@pytest.mark.parametrize(
    ("lifecycle", "status", "update_age_hours", "expected_visible"),
    [
        ("active", "active", 1, True),
        ("active", "active", 50, False),
        ("resolved", "resolved", 1, False),
        ("archived", "outcome_unknown", 1, False),
        ("needs_review", "needs_review", 1, True),
    ],
)
def test_drift_uses_canonical_public_incident_state(
    monkeypatch, lifecycle, status, update_age_hours, expected_visible,
):
    """A stale persisted active state cannot publish a search cone."""
    from core.live.feed import public_drift_collection

    now = datetime.now(timezone.utc)
    event_id = "canonical-drift-parity"
    event = IntelEvent(
        id=event_id,
        type="distress",
        severity="high",
        lat=35.5,
        lon=14.1,
        title="Reported maritime distress",
        text="Reported maritime distress",
        source="alarm_phone",
        timestamp_utc=(now - timedelta(hours=1)).isoformat(),
        metadata={
            "is_distress": True,
            "source_policy": "official_api",
            "coordinate_source": "media_ocr_text",
            "coordinate_review_status": "machine_ocr_unverified",
            "location_status": "positioned",
            "maritime_domain": "sar",
            # Legacy event state is deliberately wrong for resolved/archived
            # cases: only the canonical incident may decide public drift.
            "incident_lifecycle": "active",
        },
    )
    last_update = (now - timedelta(hours=update_age_hours)).isoformat()
    incident = {
        "incident_id": event_id,
        "lifecycle": lifecycle,
        "incident_status": status,
        "reported_at": event.timestamp_utc,
        "last_update_at": last_update,
        "state_changed_at": None,
        "resolved_at": None,
    }
    monkeypatch.setattr("core.live.feed.intel_store.persisted_events", lambda **kwargs: [])
    monkeypatch.setattr("core.live.feed.intel_store.events", lambda **kwargs: [event])
    monkeypatch.setattr(
        "core.intel.humanitarian_incident.get_incident", lambda incident_id: incident
    )
    monkeypatch.setattr(
        "core.intel.drift_service.is_auto_drift_eligible",
        lambda _event: (True, "eligible"),
    )
    monkeypatch.setattr(
        "core.intel.drift_ownership.get_current_drift_id",
        lambda _event_id: "canonical-drift-job",
    )
    fake_drift = {
        "trajectory": {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[14.0, 35.0], [14.1, 35.1]],
            },
            "properties": {},
        },
        "cone_24h": None,
        "impact_point": None,
        "metadata": {"published": True},
    }
    monkeypatch.setattr("core.db.store.get_drift", lambda _job_id: fake_drift)
    monkeypatch.setattr("core.live.feed._is_publishable_live_drift", lambda _drift: True)

    features = public_drift_collection(limit=20)["features"]
    visible = any(
        feature.get("properties", {}).get("intel_event_id") == event_id
        for feature in features
    )
    assert visible is expected_visible


def test_recent_repost_does_not_resurrect_stale_canonical_drift(monkeypatch):
    """A recent repost can retain timeline context, not revive a 50h-old drift."""
    from core.live.feed import public_drift_collection

    now = datetime.now(timezone.utc)
    event = IntelEvent(
        id="repost-stale-drift",
        type="distress",
        severity="high",
        lat=35.5,
        lon=14.1,
        title="Reported distress",
        text="Reported distress",
        source="alarm_phone",
        timestamp_utc=(now - timedelta(hours=50)).isoformat(),
        metadata={
            "is_distress": True,
            "source_policy": "official_api",
            "coordinate_source": "media_ocr_text",
            "coordinate_review_status": "machine_ocr_unverified",
            "location_status": "positioned",
            "maritime_domain": "sar",
            "incident_lifecycle": "active",
            "last_repost_at": (now - timedelta(hours=1)).isoformat(),
        },
    )
    incident = {
        "incident_id": event.id,
        "lifecycle": "active",
        "incident_status": "active",
        "reported_at": event.timestamp_utc,
        "last_update_at": event.timestamp_utc,
        "state_changed_at": None,
        "resolved_at": None,
    }
    monkeypatch.setattr("core.live.feed.intel_store.persisted_events", lambda **kwargs: [])
    monkeypatch.setattr("core.live.feed.intel_store.events", lambda **kwargs: [event])
    monkeypatch.setattr(
        "core.intel.humanitarian_incident.get_incident", lambda _id: incident
    )
    monkeypatch.setattr(
        "core.intel.drift_service.is_auto_drift_eligible",
        lambda _event: (True, "eligible"),
    )
    # If canonical status is honoured, the code never attempts drift lookup.
    def unexpected_lookup(_event_id):
        raise AssertionError("stale canonical incident must not look up a drift")

    monkeypatch.setattr(
        "core.intel.drift_ownership.get_current_drift_id", unexpected_lookup
    )
    features = public_drift_collection(limit=20)["features"]
    assert not any(
        feature.get("properties", {}).get("intel_event_id") == event.id
        for feature in features
    )
