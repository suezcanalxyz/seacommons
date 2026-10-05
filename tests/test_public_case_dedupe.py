from datetime import datetime, timedelta, timezone

from core.live.projection import dedupe_public_case_items


def _item(item_id: str, *, source: str = "Alarm Phone", title: str = "35 people in distress",
          at: datetime, lon: float = 14.0, lat: float = 35.0):
    return {
        "incident_id": item_id,
        "reported_at": at.isoformat(),
        "title": title,
        "source": source,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def test_dedupe_keeps_earlier_alarm_phone_translation():
    base = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    earlier = _item("a", at=base)
    later = _item("b", at=base + timedelta(seconds=60), title="35 persons in distress")
    result = dedupe_public_case_items([later, earlier])
    assert [row["incident_id"] for row in result] == ["a"]


def test_dedupe_does_not_collapse_outside_time_or_position_window():
    base = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    rows = [
        _item("a", at=base),
        _item("b", at=base + timedelta(seconds=121)),
        _item("c", at=base + timedelta(seconds=30), lon=14.02),
    ]
    assert {row["incident_id"] for row in dedupe_public_case_items(rows)} == {"a", "b", "c"}


def test_dedupe_leaves_unrelated_catalog_rows_untouched():
    base = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    rows = [
        _item(str(index), source="AIS", title="35 anomaly", at=base + timedelta(seconds=index))
        for index in range(2500)
    ]
    result = dedupe_public_case_items(rows)
    assert len(result) == len(rows)
