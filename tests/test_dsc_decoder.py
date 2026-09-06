from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.intel.service_taxonomy import classify_service


COMMON = {
    "receiver_id": "owrx-med-01",
    "physical_lineage": "central-med-rx-01",
    "observed_at": datetime(2026, 9, 6, 19, 0, tzinfo=timezone.utc),
    "frequency_hz": 2_187_500,
    "source_terms": "operator-permission",
    "raw_evidence_ref": "obs:dsc-raw-001",
}


def test_normalizes_distress_dsc_with_mmsi_coordinates_and_presence():
    from core.radio.dsc import normalize_dsc_decoder_message

    obs = normalize_dsc_decoder_message(
        {
            "message_id": "rx-42",
            "category": "DISTRESS",
            "mmsi": "247123456",
            "latitude": 35.5,
            "longitude": 14.2,
            "nature_code": "FIRE",
        },
        **COMMON,
    )

    assert obs.decoder_message_id == "rx-42"
    assert obs.category == "distress"
    assert obs.mmsi == "247123456"
    assert obs.latitude == 35.5
    assert obs.longitude == 14.2
    assert obs.nature_code == "fire"
    assert obs.field_presence == (
        "category",
        "latitude",
        "longitude",
        "mmsi",
        "nature_code",
    )


def test_missing_native_message_id_gets_deterministic_decoder_id():
    from core.radio.dsc import normalize_dsc_decoder_message

    payload = {"category": "urgency", "mmsi": "247000001"}
    first = normalize_dsc_decoder_message(payload, **COMMON)
    second = normalize_dsc_decoder_message(payload, **COMMON)

    assert first.decoder_message_id == second.decoder_message_id
    assert first.decoder_message_id.startswith("dsc_")


def test_unknown_codes_remain_unknown_or_bounded_without_semantic_guessing():
    from core.radio.dsc import normalize_dsc_decoder_message

    obs = normalize_dsc_decoder_message(
        {"category": "special-local-code", "nature_code": "X99-CUSTOM"},
        **COMMON,
    )
    assert obs.category == "unknown"
    assert obs.nature_code == "x99-custom"


def test_partial_coordinates_and_invalid_payload_fail_closed():
    from core.radio.dsc import normalize_dsc_decoder_message

    with pytest.raises(ValueError, match="coordinates"):
        normalize_dsc_decoder_message({"category": "distress", "latitude": 35.0}, **COMMON)
    with pytest.raises(ValueError, match="mapping"):
        normalize_dsc_decoder_message("DISTRESS", **COMMON)  # type: ignore[arg-type]


def test_dsc_classification_metadata_is_maritime_safety_never_humanitarian():
    from core.radio.dsc import dsc_classification_metadata, normalize_dsc_decoder_message

    obs = normalize_dsc_decoder_message({"category": "distress"}, **COMMON)
    metadata = dsc_classification_metadata(obs)

    assert metadata["service"] == "maritime"
    assert metadata["lane"] == "safety"
    assert "humanitarian" not in str(metadata).lower()
    classification = classify_service(metadata)
    assert classification.service == "maritime"
    assert classification.lane == "safety"


def test_non_distress_dsc_is_still_maritime_safety_context_not_humanitarian():
    from core.radio.dsc import dsc_classification_metadata, normalize_dsc_decoder_message

    obs = normalize_dsc_decoder_message({"category": "routine"}, **COMMON)
    metadata = dsc_classification_metadata(obs)
    assert metadata == {
        "service": "maritime",
        "lane": "safety",
        "observation_type": "dsc_message",
        "dsc_category": "routine",
    }
