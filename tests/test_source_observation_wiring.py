# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P0.2: SourceObservation wiring for the remaining
ingestion adapters that wrote directly to intel_store without a backing
SourceObservation (core.intel.gfw_monitor, core.intel.viirs_monitor,
core.intel.twitter_monitor -- core.intel.vessel_incident_monitor is
covered in tests/test_vessel_incidents.py).

Each test calls the adapter's own `_record_source_observation()` helper
directly -- the exact function its real poll loop calls -- and confirms
a real SourceObservationDB row exists afterward.
"""
from __future__ import annotations

import uuid

from core.db.models import SourceObservationDB
from core.db.session import session_scope
from core.intel.source_observation import observation_id


def _fetch(obs_id: str):
    with session_scope() as db:
        row = db.get(SourceObservationDB, obs_id)
        if row is None:
            return None
        return {"service": row.service, "lane": row.lane, "lat": row.lat, "lon": row.lon}


def test_gfw_monitor_records_a_source_observation():
    from core.intel import gfw_monitor

    eid = f"gfw:encounter:{uuid.uuid4()}"
    gfw_monitor._record_source_observation(
        eid, {"start": "2026-09-04T10:00:00Z", "id": "e1"}, lat=35.5, lon=14.1,
    )
    obs = _fetch(observation_id("GFW", eid))
    assert obs is not None
    assert obs["lat"] == 35.5 and obs["lon"] == 14.1


def test_viirs_monitor_records_a_source_observation():
    from core.intel import viirs_monitor

    eid = f"vbd:{uuid.uuid4()}"
    viirs_monitor._record_source_observation(
        eid, {"Rad_DNB": "12.3"}, "2026-09-04", lat=36.0, lon=15.0,
    )
    obs = _fetch(observation_id("VIIRS VBD", eid))
    assert obs is not None
    assert obs["lat"] == 36.0 and obs["lon"] == 15.0


def test_twitter_monitor_records_a_source_observation():
    from core.intel.store import IntelEvent
    from core.intel import twitter_monitor

    tweet_id = str(uuid.uuid4().int)[:15]
    post = {"id": tweet_id, "created_at": "2026-09-04T10:00:00Z", "url": "https://x.test/1"}
    event = IntelEvent(lat=34.9, lon=13.8)
    twitter_monitor._record_source_observation(post, event=event)
    obs = _fetch(observation_id("X / Twitter", tweet_id))
    assert obs is not None
    assert obs["lat"] == 34.9 and obs["lon"] == 13.8


def test_twitter_monitor_skips_when_no_tweet_id():
    """No source_id -> nothing to key an idempotent observation by; the
    helper must not raise, just skip."""
    from core.intel.store import IntelEvent
    from core.intel import twitter_monitor

    twitter_monitor._record_source_observation({}, event=IntelEvent())  # must not raise


def test_warfare_acled_records_a_source_observation():
    from core.mda import warfare

    eid = f"acled:{uuid.uuid4()}"
    warfare._record_source_observation(
        source_name="ACLED", source_id=eid, observed_at="2026-09-04T00:00:00+00:00",
        raw_payload={"event_type": "Armed clash"}, lat=35.0, lon=15.0,
    )
    obs = _fetch(observation_id("ACLED", eid))
    assert obs is not None
    assert obs["lat"] == 35.0 and obs["lon"] == 15.0


def test_warfare_nga_msi_records_a_source_observation():
    from core.mda import warfare

    wid = f"navwarn:{uuid.uuid4()}"
    warfare._record_source_observation(
        source_name="NGA MSI", source_id=wid, observed_at="2026-09-04T00:00:00+00:00",
        raw_payload={"text": "GNSS interference reported"}, lat=36.5, lon=16.0,
    )
    obs = _fetch(observation_id("NGA MSI", wid))
    assert obs is not None
    assert obs["lat"] == 36.5 and obs["lon"] == 16.0
