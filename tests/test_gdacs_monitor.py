# SPDX-License-Identifier: AGPL-3.0-or-later
"""GDACS RSS monitor: region/coordinate filtering, dedup, and the
SourceObservation adapter wiring (docs/fixes.md M1.2)."""
from __future__ import annotations

import pytest

from core.intel.gdacs_monitor import GDACSMonitor
from core.intel.store import IntelStore


def _item(**overrides) -> dict[str, str]:
    item = {
        "title": "Red alert: Tropical Cyclone",
        "description": "A tropical cyclone over the central Mediterranean.",
        "link": "https://www.gdacs.org/report.aspx?eventid=1001",
        "guid": "gdacs-1001",
        "pub_date": "Thu, 03 Sep 2026 09:00:00 GMT",
        "lat": "35.5",
        "lon": "14.0",
        "alertlevel": "Red",
        "eventtype": "TC",
        "country": "Malta",
    }
    item.update(overrides)
    return item


@pytest.fixture
def monitor(monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.gdacs_monitor.intel_store", store)
    m = GDACSMonitor()
    m._added = store  # test handle
    return m


def test_ingest_publishes_a_red_alert_inside_the_region(monitor):
    assert monitor._ingest(_item()) is True
    events = monitor._added.events()
    assert len(events) == 1
    assert events[0].type == "gdacs"
    assert events[0].severity == "critical"
    assert events[0].metadata["gdacs_alert_level"] == "red"


def test_ingest_rejects_events_outside_the_mediterranean_bbox(monitor):
    assert monitor._ingest(_item(lat="1.0", lon="1.0")) is False
    assert monitor._added.events() == []


def test_ingest_dedupes_the_same_item_within_one_process(monitor):
    item = _item()
    assert monitor._ingest(item) is True
    assert monitor._ingest(item) is False
    assert len(monitor._added.events()) == 1


def test_ingest_records_a_source_observation_independent_of_region_filtering(monkeypatch):
    """docs/fixes.md M1.2: every GDACS RSS item gets a durable
    SourceObservation, even one later rejected by the region/coordinate
    filter below -- that filter decides publication, not whether the raw
    item was received. Idempotent by guid: ingesting the same item twice
    (a fresh monitor instance, so the in-process _seen dedup doesn't
    short-circuit first) still yields exactly one observation row."""
    from core.db.models import SourceObservationDB
    from core.db.session import session_scope
    from core.intel.source_observation import observation_id

    store = IntelStore()
    monkeypatch.setattr("core.intel.gdacs_monitor.intel_store", store)

    # Outside the bbox -- never becomes an IntelEvent, but was received.
    outside = _item(guid="gdacs-outside-1", lat="1.0", lon="1.0")
    GDACSMonitor()._ingest(outside)
    GDACSMonitor()._ingest(outside)  # fresh instance -- _seen dedup does not apply

    obs_id = observation_id("GDACS", "gdacs-outside-1")
    with session_scope() as db:
        rows = db.query(SourceObservationDB).filter(
            SourceObservationDB.source_name == "GDACS",
            SourceObservationDB.source_id == "gdacs-outside-1",
        ).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.observation_id == obs_id
        assert row.service == "maritime"
        assert row.lane == "environmental"
        assert row.observation_type == "source_post"
        assert row.source_policy == "official_rss"
        assert row.lat == 1.0
        assert row.lon == 1.0

    assert store.events() == []  # confirms it really was filtered, not published


def test_ingest_still_publishes_normally_if_source_observation_write_fails(monitor, monkeypatch):
    """The observation write is best-effort and must never block real
    ingestion -- a broken DB session must not stop a valid alert from
    being published."""
    def _boom(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("core.db.session.session_scope", _boom)
    assert monitor._ingest(_item()) is True
    assert len(monitor._added.events()) == 1
