# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P0.10: Live authority cutover.

Regression fixture: before this fix, core.live.feed.public_signal_
collection and core.live_edge_publisher.public_event_from_row each
independently recomputed lifecycle from the raw IntelEvent at read
time, and neither ever exposed last_update_at/state_changed_at/
resolved_at at all -- so even after P0.9 made the canonical incident's
timer advance on a thread update, nothing public actually read it. Exit
gate: the public feed's lifecycle and timer fields come from the
canonical HumanitarianIncidentDB when one exists, VM/edge agree, and a
thread update visibly advances the public last_update_at.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.intel.humanitarian_incident import (
    get_incident,
    register,
    resolve_public_incident_state,
)
from core.intel.store import IntelEvent, intel_store

_NOW = datetime.now(timezone.utc).replace(microsecond=0)
_FOUNDING_TS = (_NOW - timedelta(hours=4)).isoformat()
_REPLY_TS = (_NOW - timedelta(hours=2, minutes=30)).isoformat()


@pytest.fixture(autouse=True)
def _fresh_tables():
    from core.db.models import HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import engine, session_scope

    HumanitarianIncidentDB.__table__.create(bind=engine(), checkfirst=True)
    IncidentTransitionDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(HumanitarianIncidentDB).delete()
        db.query(IncidentTransitionDB).delete()
    register()
    yield


def _distress_event(event_id, text, timestamp):
    # Unique text per call: intel_store.add()'s dedup keys off
    # source+title+text[:120], and intel_store is a shared, process-global
    # singleton across the whole pytest session -- a fixed string reused
    # across test files can collide with an unrelated test's event and be
    # silently dropped as a duplicate.
    unique_text = f"{text} [{event_id}]"
    return IntelEvent(
        id=event_id, type="distress", severity="high", lat=35.5, lon=14.1,
        title=unique_text[:80], text=unique_text, source="Alarm Phone", timestamp_utc=timestamp,
        metadata={
            "is_distress": True, "source_policy": "operator_published",
            "publication_status": "published",
        },
    )


def _wait_for(predicate, *, tries=40, delay=0.05):
    for _ in range(tries):
        if predicate():
            return True
        time.sleep(delay)
    return False


def test_resolve_public_incident_state_uses_the_canonical_incident_when_present():
    from core.intel.humanitarian_incident import sync_incident_for_event

    event = _distress_event(f"p010-{uuid.uuid4()}", "MAYDAY test", _FOUNDING_TS)
    sync_incident_for_event(event, lifecycle="active")

    state = resolve_public_incident_state(event, now=_NOW, same_source=[])
    incident = get_incident(event.id)
    assert state["lifecycle"] == incident["lifecycle"] == "active"
    assert state["reported_at"] == incident["reported_at"]
    assert state["last_update_at"] == incident["last_update_at"]


def test_resolve_public_incident_state_falls_back_when_no_incident_exists():
    event = _distress_event(f"p010-noincident-{uuid.uuid4()}", "Rescued! All safe.", _FOUNDING_TS)
    assert get_incident(event.id) is None

    state = resolve_public_incident_state(event, now=_NOW, same_source=[])
    assert state["lifecycle"] == "resolved"  # matches distress_lifecycle's own text-based read
    assert state["reported_at"] == event.timestamp_utc
    assert state["last_update_at"] == event.timestamp_utc
    assert state["state_changed_at"] is None
    assert state["resolved_at"] is None


def test_public_signal_collection_exposes_canonical_timer_fields():
    from core.live.feed import public_signal_collection

    event_id = f"p010-live-{uuid.uuid4()}"
    event = _distress_event(event_id, "MAYDAY live feed test", _FOUNDING_TS)
    intel_store.add(event)
    assert _wait_for(lambda: get_incident(event_id) is not None)

    collection = public_signal_collection(mode="humanitarian", limit=500, days=1)
    feature = next(f for f in collection["features"] if f["properties"]["id"] == f"intel:{event_id}")
    assert feature["properties"]["last_update_at"] == _FOUNDING_TS
    assert feature["properties"]["reported_at"] == _FOUNDING_TS


def test_a_thread_update_advances_the_public_last_update_at():
    """The end-to-end P0.9 -> P0.10 proof: a reply's own posted_at is
    visible in the public Live feed's last_update_at, not just the
    founding post's timestamp."""
    from core.live.feed import public_signal_collection

    event_id = f"p010-thread-{uuid.uuid4()}"
    event = _distress_event(event_id, "MAYDAY thread update test", _FOUNDING_TS)
    intel_store.add(event)
    assert _wait_for(lambda: get_incident(event_id) is not None)

    reply_posted_at = _REPLY_TS
    intel_store.append_thread_repost(event_id, {
        "tweet_id": f"reply-{uuid.uuid4()}", "posted_at": reply_posted_at,
        "url": "https://x.test/reply", "kind": "repost",
    })
    assert _wait_for(lambda: get_incident(event_id)["last_update_at"] == reply_posted_at)

    collection = public_signal_collection(mode="humanitarian", limit=500, days=1)
    feature = next(f for f in collection["features"] if f["properties"]["id"] == f"intel:{event_id}")
    assert feature["properties"]["last_update_at"] == reply_posted_at


def test_vm_and_edge_agree_on_the_canonical_state_for_the_same_incident():
    from core.live_edge_publisher import public_event_from_row

    event_id = f"p010-parity-{uuid.uuid4()}"
    event = _distress_event(event_id, "MAYDAY parity test", _FOUNDING_TS)
    intel_store.add(event)
    assert _wait_for(lambda: get_incident(event_id) is not None)

    vm_state = resolve_public_incident_state(event, now=_NOW, same_source=[])

    row = SimpleNamespace(
        id=event_id, type="distress", severity="high", lat=35.5, lon=14.1,
        title="MAYDAY parity test", text="MAYDAY parity test",
        url="", source="Alarm Phone", linked_mmsi="",
        timestamp_utc=_FOUNDING_TS,
        meta={
            "is_distress": True, "source_policy": "operator_published",
            "publication_status": "published",
        },
    )
    edge_payload = public_event_from_row(row, "node", now=_NOW, same_source=[])

    assert edge_payload["properties"]["incident_lifecycle"] == vm_state["lifecycle"]
    assert edge_payload["properties"]["last_update_at"] == vm_state["last_update_at"]


def test_a_maritime_safety_marker_has_no_canonical_incident_and_falls_back():
    """docs/updates.md P0.8: a beacon never gets a HumanitarianIncidentDB
    row -- resolve_public_incident_state must not crash or fabricate one,
    just fall back honestly."""
    event = IntelEvent(
        id=f"p010-safety-{uuid.uuid4()}", type="distress", severity="critical",
        lat=35.1, lon=14.2, title="Distress beacon activated", text="beacon",
        source="ais_sart", timestamp_utc=_FOUNDING_TS,
        metadata={"is_distress": True, "maritime_domain": "safety", "service": "maritime", "lane": "safety"},
    )
    assert get_incident(event.id) is None
    state = resolve_public_incident_state(event, now=_NOW, same_source=[])
    assert state["state_changed_at"] is None
    assert state["resolved_at"] is None


def test_resolve_public_incident_state_exposes_real_incident_status():
    event_id = f"p010-status-{uuid.uuid4()}"
    event = _distress_event(event_id, "MAYDAY status contract", _FOUNDING_TS)
    intel_store.add(event)
    assert _wait_for(lambda: get_incident(event_id) is not None)

    state = resolve_public_incident_state(event, now=_NOW, same_source=[])
    assert state["incident_status"] == "active"

    from core.intel.humanitarian_incident import sync_incident_for_event
    sync_incident_for_event(event, lifecycle="resolved")
    state = resolve_public_incident_state(event, now=_NOW, same_source=[])
    assert state["incident_status"] == "resolved"
