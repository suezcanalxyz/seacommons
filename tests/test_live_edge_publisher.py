from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.live_edge_publisher import Outbox, public_event_from_row, signature


def distress_row(**meta_overrides):
    meta = {"is_distress": True, "confidence": 0.72, "radius_m": 5000}
    meta.update(meta_overrides)
    return SimpleNamespace(
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
        meta=meta,
    )


def test_public_distress_event_mapping_is_versioned() -> None:
    event = public_event_from_row(distress_row(), "oracle-collector-1")

    assert event is not None
    assert event["id"].startswith("evt-1:")
    assert event["visibility"] == "public"
    assert event["type"] == "distress_observation"
    assert event["geometry"]["coordinates"] == [14.2, 35.1]
    assert event["properties"]["incident_id"] == "evt-1"
    assert event["properties"]["radius_m"] == 5000


def test_material_update_gets_new_version_id() -> None:
    first = public_event_from_row(distress_row(), "node")
    second = public_event_from_row(distress_row(confidence=0.9), "node")

    assert first is not None and second is not None
    assert first["id"] != second["id"]
    assert first["properties"]["incident_id"] == second["properties"]["incident_id"]


def test_resolved_event_becomes_removal_update() -> None:
    event = public_event_from_row(distress_row(resolved=True), "node")

    assert event is not None
    assert event["type"] == "incident_resolved"
    assert event["properties"]["resolved"] is True


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
