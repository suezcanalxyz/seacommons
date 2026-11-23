# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regressions for canonical lifecycle and provider identity in Live Drift."""

from datetime import datetime, timedelta, timezone

import pytest

from core.intel.store import IntelEvent
from core.live.feed import public_drift_collection


def _distress(event_id: str, source: str, *, minutes: int = 0, lifecycle: str = "active") -> IntelEvent:
    return IntelEvent(
        id=event_id,
        type="distress",
        severity="high",
        lat=35.0,
        lon=14.0,
        title="Urgent distress near Malta",
        text="Urgent distress near Malta",
        source=source,
        timestamp_utc=(datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(),
        metadata={
            "is_distress": True,
            "maritime_domain": "sar",
            "source_policy": "operator_published",
            "incident_lifecycle": lifecycle,
        },
    )


def _feed_events(monkeypatch, events: list[IntelEvent]) -> None:
    monkeypatch.setattr("core.live.feed.intel_store.persisted_events", lambda **_kwargs: [])
    monkeypatch.setattr("core.live.feed.intel_store.events", lambda **_kwargs: events)
    # This regression exercises lifecycle selection, not the separately tested
    # source-publication policy or drift model geometry.
    monkeypatch.setattr(
        "core.live.feed._public_intel_feature",
        lambda event, **_kwargs: {"type": "Feature"} if event.id == events[0].id else None,
    )


@pytest.mark.parametrize(
    ("stale_metadata_state", "canonical_state", "incident_status", "should_consult_drift"),
    [
        ("active", "resolved", "resolved", False),
        ("resolved", "needs_review", "needs_review", True),
        ("active", "archived", "outcome_unknown", False),
        ("active", "active", "outcome_unknown", False),
    ],
)
def test_canonical_lifecycle_overrides_stale_drift_metadata(
    monkeypatch, stale_metadata_state, canonical_state, incident_status, should_consult_drift,
):
    event = _distress("canonical-drift-regression", "Alarm Phone", lifecycle=stale_metadata_state)
    _feed_events(monkeypatch, [event])
    monkeypatch.setattr(
        "core.intel.humanitarian_incident.resolve_public_incident_state",
        lambda _event, *, now, same_source: {
            "lifecycle": canonical_state, "incident_status": incident_status,
        },
    )
    monkeypatch.setattr(
        "core.intel.drift_service.is_auto_drift_eligible",
        lambda _event: (True, "eligible"),
    )
    consulted = []

    def current_drift(event_id):
        consulted.append(event_id)
        return None

    monkeypatch.setattr("core.intel.drift_ownership.get_current_drift_id", current_drift)
    collection = public_drift_collection(limit=5)

    assert collection["features"] == []
    assert consulted == ([event.id] if should_consult_drift else [])


def test_legacy_drift_followup_groups_casefolded_provider_names(monkeypatch):
    origin = _distress("provider-origin", "Alarm Phone", lifecycle="")
    followup = _distress("provider-followup", " ALARM PHONE ", minutes=1, lifecycle="")
    _feed_events(monkeypatch, [origin, followup])
    monkeypatch.setattr(
        "core.intel.humanitarian_incident.resolve_public_incident_state",
        lambda event, *, now, same_source: {
            "lifecycle": lifecycle_for(event, now=now, same_source=same_source),
            "incident_status": "resolved",
        },
    )
    seen = []

    def lifecycle_for(event, *, now, same_source):
        seen.append((event.id, [candidate.id for candidate in same_source]))
        return "resolved"

    # The shared resolver is exercised above with the candidate provider set.
    monkeypatch.setattr(
        "core.intel.drift_ownership.get_current_drift_id",
        lambda _event_id: pytest.fail("resolved drift must not consult a current job"),
    )

    collection = public_drift_collection(limit=5)

    assert collection["features"] == []
    assert seen == [(origin.id, [origin.id, followup.id])]
