# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md section 7 -- a process restart preserves durable events,
their canonical classification, their lifecycle state and their repaired
locations.

The in-memory ``deque`` is a cache, not the record. After a restart it is
empty and ``load_from_db()`` rehydrates it from ``intel_events``. This test
drives a full write path (ingest -> enrich location -> lifecycle update),
throws the in-memory store away, reloads from the DB and proves nothing the
operator saw before the restart has been lost or silently downgraded.

Also covers section 4 smoke item 16: an event that never occupied a slot in
the bounded deque still reaches the reloaded store.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from core.db.models import IntelEventDB
from core.db.session import session_scope
from core.intel.drift_service import is_auto_drift_eligible
from core.intel.store import IntelEvent, IntelStore
from sqlalchemy import select


def _recent(hours: float = 1.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _row(event_id: str):
    with session_scope() as db:
        row = db.execute(
            select(IntelEventDB).where(IntelEventDB.id == event_id)
        ).scalar_one_or_none()
        if row is not None:
            db.expunge(row)
        return row


def test_restart_preserves_events_classification_lifecycle_and_repaired_location():
    pre = IntelStore()

    event = IntelEvent(
        id="restart-ap-1",
        type="twitter",
        severity="critical",
        title="Alarm Phone: ~37 people in distress, Central Med",
        text="~37 people in urgent distress in the Central Mediterranean",
        source="Alarm Phone",
        url="https://x.com/i/web/status/2100000000000000001",
        timestamp_utc=_recent(),
        metadata={
            "is_distress": True,
            "tracked_account": "alarm_phone",
            "source_policy": "operator_published",
            "publication_status": "published",
            "humanitarian_case_type": "distress",
            "incident_lifecycle": "active",
            # region-only at first: OCR has not run yet
            "coordinate_source": "region_area",
            "location_status": "region_only",
            "location_uncertainty_m": 60000,
            "tweet_id": "2100000000000000001",
        },
    )
    assert pre.add(event) is True

    # OCR later extracts a real point -> the location is "repaired".
    assert pre.enrich_location(
        "restart-ap-1",
        lat=34.2715,
        lon=11.9423,
        metadata={
            "coordinate_source": "media_ocr_text",
            "coordinate_review_status": "machine_ocr_unverified",
            "location_status": "positioned",
            "location_uncertainty_m": 1500,
        },
    ) is True

    # lifecycle advances to a human-review hold.
    assert pre.update_metadata(
        "restart-ap-1", metadata={"incident_lifecycle": "needs_review"}
    ) is True

    assert _wait_until(
        lambda: (r := _row("restart-ap-1")) is not None
        and r.lat is not None
        and (r.meta or {}).get("incident_lifecycle") == "needs_review"
    ), "durable row never reached the expected pre-restart state"

    eligibility_before = is_auto_drift_eligible(
        next(e for e in pre._events if e.id == "restart-ap-1")
    )

    # ---- restart: brand-new store, empty deque, rehydrate from the DB ----
    post = IntelStore()
    assert len(post._events) == 0
    loaded = post.load_from_db(max_age_days=2)
    assert loaded >= 1

    reloaded = next((e for e in post._events if e.id == "restart-ap-1"), None)
    assert reloaded is not None, "durable event did not survive the restart"

    # repaired location
    assert reloaded.lat == 34.2715 and reloaded.lon == 11.9423
    assert reloaded.metadata["coordinate_source"] == "media_ocr_text"
    assert reloaded.metadata["coordinate_review_status"] == "machine_ocr_unverified"
    assert reloaded.metadata["location_status"] == "positioned"
    assert float(reloaded.metadata["location_uncertainty_m"]) == 1500.0
    # the stale region-only area must not resurrect
    assert "area_geojson" not in reloaded.metadata

    # classification
    assert reloaded.maritime_domain() == "sar"
    assert reloaded.tier() == "operational"
    assert reloaded.metadata["humanitarian_case_type"] == "distress"

    # lifecycle
    assert reloaded.metadata["incident_lifecycle"] == "needs_review"

    # behaviour is identical across the restart
    assert is_auto_drift_eligible(reloaded) == eligibility_before

    # canonical columns remain answerable in SQL without decoding JSON
    row = _row("restart-ap-1")
    assert row.maritime_domain == "sar"
    assert row.operational_tier == "operational"
    assert row.humanitarian_case_type == "distress"
    assert row.coordinate_review_status == "machine_ocr_unverified"
    assert float(row.location_uncertainty_m) == 1500.0


def test_restart_reload_reseeds_dedup_so_re_ingestion_makes_no_second_marker():
    pre = IntelStore()
    assert pre.add(IntelEvent(
        id="restart-ap-2",
        type="twitter",
        severity="critical",
        title="Alarm Phone: boat in distress off Lampedusa",
        text="boat in distress",
        source="Alarm Phone",
        url="https://x.com/i/web/status/2100000000000000002",
        timestamp_utc=_recent(),
        metadata={
            "is_distress": True,
            "tracked_account": "alarm_phone",
            "tweet_id": "2100000000000000002",
        },
    )) is True

    post = IntelStore()
    post.load_from_db(max_age_days=2)

    # the same tweet re-seen by the catch-up poll must be recognised as a dup
    assert "x:2100000000000000002" in post._seen
    reingest = IntelEvent(
        id="fresh-id-after-restart",
        type="twitter",
        title="Alarm Phone: boat in distress off Lampedusa",
        text="boat in distress",
        url="https://x.com/i/web/status/2100000000000000002",
        metadata={"tweet_id": "2100000000000000002"},
    )
    assert post.add(reingest, dedup_key="x:2100000000000000002") is False


def test_intel_store_persistence_mutations_are_fifo(monkeypatch):
    """DB writes for one store must preserve mutation order under async runtime mode."""
    monkeypatch.setenv("SEACOMMONS_INTEL_PERSIST_SYNC", "false")
    store = IntelStore()
    order: list[str] = []

    def persist_add(_event):
        time.sleep(0.02)
        order.append("add")

    def persist_location(*_args):
        time.sleep(0.08)
        order.append("location")

    def persist_metadata(*_args):
        order.append("metadata")

    monkeypatch.setattr(store, "_persist_sync", persist_add)
    monkeypatch.setattr(store, "_persist_location_sync", persist_location)
    monkeypatch.setattr(store, "_persist_metadata_sync", persist_metadata)

    assert store.add(IntelEvent(id="fifo-1", type="twitter", title="fifo")) is True
    assert store.enrich_location(
        "fifo-1",
        lat=34.0,
        lon=12.0,
        metadata={"coordinate_source": "media_ocr_text", "location_uncertainty_m": 1500},
    ) is True
    assert store.update_metadata("fifo-1", metadata={"incident_lifecycle": "needs_review"}) is True

    assert _wait_until(lambda: len(order) == 3)
    assert order == ["add", "location", "metadata"]
