from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone

import pytest


def _base():
    return {
        "receiver_id": "OpenWebRX Med 01",
        "physical_lineage": "Central Med RX 01",
        "observed_at": datetime(2026, 9, 6, 18, 30, tzinfo=timezone.utc),
        "frequency_hz": 2_187_500,
        "source_terms": "operator-permission",
        "raw_evidence_ref": "obs:radio-structured-001",
        "decoder_message_id": "decoder-msg-001",
    }


def test_dsc_contract_normalizes_identity_and_unknown_category_without_guessing():
    from core.radio.structured import DSCObservation

    obs = DSCObservation(
        **_base(),
        category="piracy-special",
        mmsi="  247123456 ",
        latitude=35.5,
        longitude=14.2,
        nature_code="fire",
    )

    assert obs.receiver_id == "openwebrx_med_01"
    assert obs.physical_lineage == "central_med_rx_01"
    assert obs.category == "unknown"
    assert obs.mmsi == "247123456"
    assert obs.latitude == 35.5
    assert obs.longitude == 14.2


def test_dsc_contract_is_immutable_and_has_no_humanitarian_shortcut():
    from core.radio.structured import DSCObservation

    obs = DSCObservation(**_base(), category="distress")
    with pytest.raises(FrozenInstanceError):
        obs.category = "routine"  # type: ignore[misc]

    names = {field.name for field in fields(DSCObservation)}
    assert "service" not in names
    assert "humanitarian" not in names
    assert "lifecycle" not in names
    assert "publication" not in names


@pytest.mark.parametrize("field", ["receiver_id", "physical_lineage", "decoder_message_id", "raw_evidence_ref"])
def test_dsc_required_identity_fields_fail_closed(field):
    from core.radio.structured import DSCObservation

    kwargs = _base()
    kwargs[field] = ""
    with pytest.raises(ValueError):
        DSCObservation(**kwargs, category="distress")


def test_dsc_frequency_coordinates_and_time_validate():
    from core.radio.structured import DSCObservation

    with pytest.raises(ValueError, match="frequency"):
        DSCObservation(**{**_base(), "frequency_hz": 0}, category="distress")
    with pytest.raises(ValueError, match="coordinates"):
        DSCObservation(**_base(), category="distress", latitude=35.0)
    with pytest.raises(ValueError, match="latitude"):
        DSCObservation(**_base(), category="distress", latitude=95.0, longitude=14.0)
    with pytest.raises(ValueError, match="timezone"):
        DSCObservation(
            **{**_base(), "observed_at": datetime(2026, 9, 6, 18, 30)},
            category="distress",
        )


def test_navtex_contract_preserves_bounded_structured_context_only():
    from core.radio.structured import NAVTEXObservation

    obs = NAVTEXObservation(
        **{**_base(), "frequency_hz": 518_000},
        station_id="M",
        subject_id="B",
        message_id="42",
        area="mediterranean",
        text="GALE WARNING FOR CENTRAL MEDITERRANEAN",
    )

    assert obs.station_id == "M"
    assert obs.subject_id == "B"
    assert obs.message_id == "42"
    assert obs.text == "GALE WARNING FOR CENTRAL MEDITERRANEAN"
    names = {field.name for field in fields(NAVTEXObservation)}
    assert "lifecycle" not in names
    assert "publication" not in names
    assert "humanitarian" not in names


def test_navtex_text_and_identifiers_are_bounded_and_required():
    from core.radio.structured import NAVTEXObservation

    with pytest.raises(ValueError, match="station_id"):
        NAVTEXObservation(
            **{**_base(), "frequency_hz": 518_000},
            station_id="",
            subject_id="B",
            message_id="42",
            area=None,
            text="test",
        )

    obs = NAVTEXObservation(
        **{**_base(), "frequency_hz": 518_000},
        station_id="M",
        subject_id="B",
        message_id="42",
        area="mediterranean",
        text="x" * 20_000,
    )
    assert len(obs.text) == 8192
