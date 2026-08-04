from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from core.live_edge_publisher import Outbox, public_event_from_row, signature

_NOW = datetime(2026, 8, 2, 12, 30, tzinfo=timezone.utc)


def distress_row(*, timestamp_utc="2026-08-02T12:00:00+00:00", text="Public source report", **meta_overrides):
    meta = {"is_distress": True, "confidence": 0.72, "location_uncertainty_m": 5000}
    meta.update(meta_overrides)
    return SimpleNamespace(
        id="evt-1",
        type="distress",
        severity="critical",
        lat=35.1,
        lon=14.2,
        title="Boat in distress",
        text=text,
        url="https://example.test/report",
        source="alarm_phone",
        linked_mmsi="",
        timestamp_utc=timestamp_utc,
        meta=meta,
    )


def test_public_distress_event_mapping_is_versioned() -> None:
    event = public_event_from_row(distress_row(), "oracle-collector-1", now=_NOW, same_source=[])

    assert event is not None
    assert event["id"].startswith("evt-1:")
    assert event["visibility"] == "public"
    assert event["type"] == "distress_observation"
    assert event["geometry"]["coordinates"] == [14.2, 35.1]
    assert event["properties"]["incident_id"] == "evt-1"
    assert event["properties"]["radius_m"] == 5000
    assert event["properties"]["incident_lifecycle"] == "active"


def test_material_update_gets_new_version_id() -> None:
    first = public_event_from_row(distress_row(), "node", now=_NOW, same_source=[])
    second = public_event_from_row(distress_row(confidence=0.9), "node", now=_NOW, same_source=[])

    assert first is not None and second is not None
    assert first["id"] != second["id"]
    assert first["properties"]["incident_id"] == second["properties"]["incident_id"]


def test_concluded_report_becomes_resolved_but_stays_visible() -> None:
    # Same semantics as core/api/routes/live.py: a known outcome (rescued,
    # or "found + remain missing") colors the marker green — it must NOT be
    # removed from the edge outright the way the old resolved/archived flags
    # used to trigger immediate deletion.
    row = distress_row(text="Rescued!! Thank you Ocean Viking for rescuing the 14 people")
    event = public_event_from_row(row, "node", now=_NOW, same_source=[])

    assert event is not None
    assert event["properties"]["incident_lifecycle"] == "resolved"
    assert event["type"] != "incident_removed"
    assert event["properties"]["expired"] is False


def test_stale_unresolved_report_turns_archived_not_removed() -> None:
    old_timestamp = (_NOW - timedelta(hours=30)).isoformat()
    row = distress_row(timestamp_utc=old_timestamp)
    event = public_event_from_row(row, "node", now=_NOW, same_source=[])

    assert event is not None
    assert event["properties"]["incident_lifecycle"] == "archived"
    assert event["type"] != "incident_removed"


def test_event_past_the_live_window_is_marked_for_removal() -> None:
    old_timestamp = (_NOW - timedelta(days=8)).isoformat()
    row = distress_row(timestamp_utc=old_timestamp)
    event = public_event_from_row(row, "node", now=_NOW, same_source=[])

    assert event is not None
    assert event["type"] == "incident_removed"
    assert event["properties"]["expired"] is True


def test_blocked_source_policy_never_reaches_the_edge_even_if_flagged_distress() -> None:
    # Same guarantee as core/api/routes/live.py's blocklist: a legacy scraper
    # record or an "unofficial" transport must never surface on the public
    # map, even if is_distress/publication_status say otherwise. This is the
    # primary live.seacommons.org path, so it needs the same guarantee the
    # VM standby path already has.
    for overrides in (
        {"source_policy": "unofficial"},
        {"via": "nitter"},
        {"scrape_source": "twscrape-mirror"},
    ):
        row = distress_row(**overrides)
        assert public_event_from_row(row, "node", now=_NOW, same_source=[]) is None


def test_row_without_distress_flag_or_explicit_publication_is_not_exported() -> None:
    # Mirrors the VM path: a bare row with no is_distress flag, a non-distress
    # type, and no explicit publication decision must not leak onto the
    # public map.
    row = distress_row(is_distress=False)
    row.type = "news"
    assert public_event_from_row(row, "node", now=_NOW, same_source=[]) is None


def test_explicit_publication_without_is_distress_flag_is_exported() -> None:
    # The publication_status=="published" branch (fixed from a "publication_state"
    # typo that was never set by any producer and was therefore always False)
    # must actually work: an explicitly published non-distress row still needs
    # a path onto the public map.
    row = distress_row(is_distress=False, publication_status="published")
    row.type = "ngo_activity"
    assert public_event_from_row(row, "node", now=_NOW, same_source=[]) is not None


def test_non_public_context_event_is_not_exported() -> None:
    row = SimpleNamespace(
        id="evt-2",
        type="news",
        severity="low",
        lat=None,
        lon=None,
        title="Context",
        text="Not explicitly published",
        url="",
        source="news",
        linked_mmsi="",
        timestamp_utc="2026-08-02T12:00:00+00:00",
        meta={},
    )

    assert public_event_from_row(row, "node", now=_NOW, same_source=[]) is None


def test_outbox_survives_reopen_and_remembers_delivery(tmp_path: Path) -> None:
    path = tmp_path / "outbox.db"
    first = Outbox(path)
    assert first.enqueue("evt-3:v1", {"id": "evt-3:v1", "type": "distress_observation"})

    second = Outbox(path)
    assert second.counts()["pending"] == 1
    assert second.ready(10)[0]["event_id"] == "evt-3:v1"

    second.acknowledge("evt-3:v1")
    third = Outbox(path)
    assert third.counts()["pending"] == 0
    assert third.enqueue("evt-3:v1", {"id": "evt-3:v1"}) is False


def test_signature_is_stable() -> None:
    assert signature("secret", '{"id":"evt"}') == signature("secret", '{"id":"evt"}')
    assert signature("secret", '{"id":"evt"}') != signature("other", '{"id":"evt"}')
