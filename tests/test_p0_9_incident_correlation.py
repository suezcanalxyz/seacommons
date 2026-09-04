# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P0.9: Canonical incident correlation (emergency
Humanitarian cutover sequence).

Regression fixture for a real gap: core.intel.store.append_thread_repost
(the SAME entry point core.intel.twikit_monitor's reply/repost/quote/
translation-twin/self-reply-resolution threading all converge on --
"a repost/reply must answer the SAME thread, never spawn a new marker")
never notified intel_store's subscriber fan-out, so
core.intel.humanitarian_incident's canonical HumanitarianIncidentDB
(last_update_at, lifecycle) went stale on every Alarm Phone thread
update even though the live feed's own read-time recomputation already
reflected it correctly. Exit gate: a reply/repost/later update attaches
to the SAME incident (never creates a second one) and actually advances
its canonical last_update_at / lifecycle.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.intel.humanitarian_incident import get_incident, list_transitions, register
from core.intel.store import IntelEvent, intel_store


@pytest.fixture(autouse=True)
def _fresh_tables():
    from core.db.models import HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import engine, session_scope

    HumanitarianIncidentDB.__table__.create(bind=engine(), checkfirst=True)
    IncidentTransitionDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(HumanitarianIncidentDB).delete()
        db.query(IncidentTransitionDB).delete()
    register()  # idempotent subscribe, same as bootstrap
    yield


def _distress_event(event_id, text, timestamp):
    return IntelEvent(
        id=event_id, type="distress", severity="high", lat=35.5, lon=14.1,
        title=text[:80], text=text, source="Alarm Phone", timestamp_utc=timestamp,
        metadata={"is_distress": True},
    )


def _wait_for(predicate, *, tries=40, delay=0.05):
    for _ in range(tries):
        if predicate():
            return True
        time.sleep(delay)
    return False


def test_a_verified_reply_advances_the_canonical_incident_without_a_second_row():
    event_id = f"p09-{uuid.uuid4()}"
    founding_ts = "2026-09-04T08:00:00+00:00"
    event = _distress_event(event_id, "MAYDAY 30 people taking water off Libya", founding_ts)
    intel_store.add(event)

    assert _wait_for(lambda: get_incident(event_id) is not None)
    before = get_incident(event_id)
    assert before["last_update_at"] == founding_ts
    assert before["lifecycle"] == "active"

    reply_posted_at = "2026-09-04T09:30:00+00:00"
    intel_store.append_thread_repost(event_id, {
        "tweet_id": f"reply-{uuid.uuid4()}", "posted_at": reply_posted_at,
        "url": "https://x.test/reply", "kind": "reply", "note": "Rescued! All safe.",
    })

    assert _wait_for(lambda: get_incident(event_id)["lifecycle"] == "resolved")
    after = get_incident(event_id)
    assert after["last_update_at"] == reply_posted_at
    assert after["lifecycle"] == "resolved"

    from core.db.models import HumanitarianIncidentDB
    from core.db.session import session_scope

    with session_scope() as db:
        assert db.query(HumanitarianIncidentDB).count() == 1  # never a second incident


def test_a_plain_repost_with_no_note_advances_the_timer_without_forcing_resolution():
    event_id = f"p09-{uuid.uuid4()}"
    founding_ts = "2026-09-04T08:00:00+00:00"
    event = _distress_event(event_id, "distress report, position uncertain", founding_ts)
    intel_store.add(event)
    assert _wait_for(lambda: get_incident(event_id) is not None)

    repost_posted_at = "2026-09-04T08:45:00+00:00"
    intel_store.append_thread_repost(event_id, {
        "tweet_id": f"rt-{uuid.uuid4()}", "posted_at": repost_posted_at,
        "url": "https://x.test/rt", "kind": "repost",
    })

    assert _wait_for(lambda: get_incident(event_id)["last_update_at"] == repost_posted_at)
    after = get_incident(event_id)
    assert after["lifecycle"] == "active"  # a silent echo never forces a lifecycle change
    assert after["revision"] >= 2


def test_multiple_thread_updates_still_produce_exactly_one_incident():
    event_id = f"p09-{uuid.uuid4()}"
    event = _distress_event(event_id, "MAYDAY multiple updates test", "2026-09-04T08:00:00+00:00")
    intel_store.add(event)
    assert _wait_for(lambda: get_incident(event_id) is not None)

    for i in range(4):
        intel_store.append_thread_repost(event_id, {
            "tweet_id": f"rt-{i}-{uuid.uuid4()}",
            "posted_at": f"2026-09-04T0{8 + i}:15:00+00:00",
            "url": f"https://x.test/rt{i}", "kind": "repost",
        })
    time.sleep(0.3)

    from core.db.models import HumanitarianIncidentDB
    from core.db.session import session_scope

    with session_scope() as db:
        rows = db.query(HumanitarianIncidentDB).filter(
            HumanitarianIncidentDB.incident_id == event_id
        ).all()
        assert len(rows) == 1


def test_an_out_of_order_repost_never_moves_the_timer_backward():
    event_id = f"p09-{uuid.uuid4()}"
    event = _distress_event(event_id, "MAYDAY out of order test", "2026-09-04T10:00:00+00:00")
    intel_store.add(event)
    assert _wait_for(lambda: get_incident(event_id) is not None)

    later_reply_at = "2026-09-04T12:00:00+00:00"
    intel_store.append_thread_repost(event_id, {
        "tweet_id": f"a-{uuid.uuid4()}", "posted_at": later_reply_at,
        "url": "https://x.test/a", "kind": "repost",
    })
    assert _wait_for(lambda: get_incident(event_id)["last_update_at"] == later_reply_at)

    earlier_delayed_reply_at = "2026-09-04T10:30:00+00:00"
    intel_store.append_thread_repost(event_id, {
        "tweet_id": f"b-{uuid.uuid4()}", "posted_at": earlier_delayed_reply_at,
        "url": "https://x.test/b", "kind": "repost",
    })
    time.sleep(0.2)

    assert get_incident(event_id)["last_update_at"] == later_reply_at  # never moved backward
