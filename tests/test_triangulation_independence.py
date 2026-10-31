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


@pytest.mark.parametrize(
    ("spike_type", "role", "org", "expected"),
    [
        ("sudden_stop", "SAR", "Rescue NGO", None),
        ("vessel_loiter", "coastguard", "Coastguard", None),
        ("possible_rescue_cluster", "SAR", "Rescue NGO", None),
        ("rescue_cluster", "cargo", "Shipping Company", None),
        ("rescue_cluster", "", "Unverified Organisation", None),
        ("rescue_cluster", "rescue", "", "ais_rescue_movement"),
        ("ngo_search_pattern", "SAR", "", "ais_rescue_movement"),
        ("ngo_search_pattern", "coastguard", "", "ais_rescue_movement"),
    ],
)
def test_ais_sar_channel_requires_rescue_specificity_and_responder(
    spike_type, role, org, expected
) -> None:
    event = IntelEvent(
        id=f"spike-{spike_type}-{role}", type="ais_spike", severity="medium",
        lat=35.51, lon=14.11, title="AIS observation", source="mda",
        timestamp_utc=_ts(),
        metadata={"spike_type": spike_type, "vessel_role": role, "org": org},
    )
    assert triangulation.channel_of(event) == expected


def test_rescue_cluster_with_registry_confirmed_mmsi_accepts_missing_role() -> None:
    event = IntelEvent(
        id="registry-responder", type="ais_spike", severity="medium",
        lat=35.51, lon=14.11, title="AIS rescue cluster", source="mda",
        timestamp_utc=_ts(), linked_mmsi="258479000",
        metadata={"spike_type": "rescue_cluster"},
    )
    assert triangulation.channel_of(event) == "ais_rescue_movement"


def test_generic_ngo_stop_cannot_corroborate_distress() -> None:
    _add(IntelEvent(
        id="x-distress-stop", type="twitter", severity="high",
        lat=35.5, lon=14.1, title="Independent distress report",
        source="@alarm_phone", timestamp_utc=_ts(),
        metadata={"platform": "x", "coordinate_source": "post_text"},
    ))
    stop = _add(IntelEvent(
        id="ais-ngo-stop", type="ais_spike", severity="medium",
        lat=35.51, lon=14.11, title="NGO vessel stopped", source="mda",
        timestamp_utc=_ts(), linked_mmsi="258479000",
        metadata={"spike_type": "sudden_stop", "vessel_role": "SAR", "org": "SOS Mediterranee"},
    ))
    assert triangulation.channel_of(stop) is None
    assert triangulation.evaluate(stop) is None


def test_generic_cargo_cluster_cannot_corroborate_distress() -> None:
    _add(IntelEvent(
        id="x-distress-cluster", type="twitter", severity="high",
        lat=35.5, lon=14.1, title="Independent distress report",
        source="@alarm_phone", timestamp_utc=_ts(),
        metadata={"platform": "x", "coordinate_source": "post_text"},
    ))
    cluster = _add(IntelEvent(
        id="ais-cargo-cluster", type="ais_spike", severity="medium",
        lat=35.51, lon=14.11, title="Two cargo vessels converged", source="mda",
        timestamp_utc=_ts(), linked_mmsi="123456789",
        metadata={"spike_type": "rescue_cluster", "vessel_role": "cargo", "org": "Shipping Company"},
    ))
    assert triangulation.channel_of(cluster) is None
    assert triangulation.evaluate(cluster) is None


def test_embedded_triangulation_smoke_uses_responder_qualified_ais() -> None:
    # Keep the module's CLI smoke test exercised by pytest after SAR
    # specificity changes; a generic AIS cluster must no longer pass.
    triangulation.test_triangulation()
