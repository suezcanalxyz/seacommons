from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.live_edge_publisher import Outbox, public_event_from_row, signature


def test_public_distress_event_mapping() -> None:
    row = SimpleNamespace(
        id="evt-1",
        type="distress",
        severity="critical",
        lat=35.1,
        lon=14.2,
        title="Boat in distress",
        text="Public source report",
        url="https://example.test/report",
        source="alarm_phone",
        linked_mmsi="",
        timestamp_utc="2026-08-02T12:00:00+00:00",
        meta={"is_distress": True, "confidence": 0.72, "radius_m": 5000},
    )

    event = public_event_from_row(row, "oracle-collector-1")

    assert event is not None
    assert event["id"] == "evt-1"
    assert event["visibility"] == "public"
    assert event["type"] == "distress_observation"
    assert event["geometry"]["coordinates"] == [14.2, 35.1]
    assert event["properties"]["radius_m"] == 5000


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

    assert public_event_from_row(row, "node") is None


def test_outbox_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "outbox.db"
    first = Outbox(path)
    first.enqueue("evt-3", {"id": "evt-3", "type": "distress_observation"})
    first.set_cursor("2026-08-02T12:00:00+00:00")

    second = Outbox(path)

    assert second.get_cursor() == "2026-08-02T12:00:00+00:00"
    assert second.counts()["pending"] == 1
    assert second.ready(10)[0]["event_id"] == "evt-3"


def test_signature_is_stable() -> None:
    assert signature("secret", '{"id":"evt"}') == signature("secret", '{"id":"evt"}')
    assert signature("secret", '{"id":"evt"}') != signature("other", '{"id":"evt"}')
