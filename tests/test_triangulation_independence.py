from datetime import datetime, timezone

import pytest

from core.intel import triangulation
from core.intel.store import IntelEvent, intel_store


@pytest.fixture(autouse=True)
def _clean_store():
    with intel_store._lock:
        intel_store._events.clear()
        intel_store._seen.clear()
    yield
    with intel_store._lock:
        intel_store._events.clear()
        intel_store._seen.clear()


def _add(event: IntelEvent) -> IntelEvent:
    intel_store.add(event)
    return event


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()

def test_x_text_and_x_ocr_are_not_independent_corroboration() -> None:
    text = _add(IntelEvent(
        id="x-text", type="twitter", severity="high",
        lat=35.5, lon=14.1, title="Distress report", source="@alarm_phone",
        timestamp_utc=_ts(),
        metadata={"platform": "x", "coordinate_source": "post_text"},
    ))
    ocr = _add(IntelEvent(
        id="x-ocr", type="twitter", severity="high",
        lat=35.5, lon=14.1, title="OCR coordinates", source="@alarm_phone",
        timestamp_utc=_ts(),
        metadata={"platform": "x", "coordinate_source": "media_ocr_consensus"},
    ))

    assert triangulation.channel_of(text) == "alarmphone_text"
    assert triangulation.channel_of(ocr) == "media_ocr_consensus"
    assert triangulation.evaluate(ocr) is None


def test_x_plus_ais_rescue_movement_remains_independent_corroboration() -> None:
    _add(IntelEvent(
        id="x-distress", type="twitter", severity="high",
        lat=35.5, lon=14.1, title="Distress report", source="@alarm_phone",
        timestamp_utc=_ts(),
        metadata={"platform": "x", "coordinate_source": "post_text"},
    ))
    ais = _add(IntelEvent(
        id="ais-rescue", type="ais_spike", severity="medium",
        lat=35.51, lon=14.11, title="Rescue vessel search pattern", source="mda",
        timestamp_utc=_ts(), linked_mmsi="209888000",
        metadata={"spike_type": "rescue_cluster", "vessel_role": "rescue"},
    ))

    summary = triangulation.evaluate(ais)

    assert summary is not None
    assert summary["verification_status"] == "multi_source_corroborated"
    assert set(summary["corroborating_event_ids"]) == {"x-distress", "ais-rescue"}
