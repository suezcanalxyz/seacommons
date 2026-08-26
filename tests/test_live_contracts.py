# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

import pytest
from core.domain.live_contracts import (
    IncidentLifecycle,
    LiveSignalFeature,
    LiveSignalKind,
    LocationPrecision,
    PublicationStatus,
    SourcePolicy,
)
from core.intel.store import IntelEvent
from core.live.projection import _public_intel_feature
from jsonschema import (
    Draft202012Validator,
    FormatChecker,
)
from jsonschema import (
    ValidationError as JsonSchemaError,
)
from pydantic import ValidationError
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "docs" / "contracts"


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    domain = _load("live-domain-v1.schema.json")
    registry = Registry().with_resource(domain["$id"], Resource.from_contents(domain))
    return Draft202012Validator(
        _load(name),
        registry=registry,
        format_checker=FormatChecker(),
    )


def _public_event(**metadata) -> IntelEvent:
    return IntelEvent(
        id="contract-event-01",
        type="distress",
        severity="high",
        title="Reported maritime distress",
        source="Alarm Phone",
        timestamp_utc="2026-08-26T10:00:00+00:00",
        metadata={
            "source_policy": "official_site_embed",
            "is_distress": True,
            **metadata,
        },
    )


def test_live_domain_schema_matches_backend_enums() -> None:
    definitions = _load("live-domain-v1.schema.json")["$defs"]
    assert definitions["publication_status"]["enum"] == [
        item.value for item in PublicationStatus
    ]
    assert definitions["incident_lifecycle"]["enum"] == [
        item.value for item in IncidentLifecycle
    ]
    assert definitions["live_signal_kind"]["enum"] == [
        item.value for item in LiveSignalKind
    ]
    assert definitions["source_policy"]["enum"] == [item.value for item in SourcePolicy]
    assert definitions["location_precision"]["enum"] == [
        item.value for item in LocationPrecision
    ]


@pytest.mark.parametrize(
    ("geometry", "metadata", "precision"),
    [
        (None, {}, "unpositioned"),
        (
            {
                "type": "Polygon",
                "coordinates": [
                    [[14.0, 35.0], [14.2, 35.0], [14.1, 35.2], [14.0, 35.0]]
                ],
            },
            {"area_confidence": "area_low_confidence"},
            "area_low_confidence",
        ),
    ],
)
def test_live_signal_contract_accepts_real_unpositioned_and_area_projection(
    geometry: dict | None,
    metadata: dict,
    precision: str,
) -> None:
    event = _public_event(**metadata)
    if geometry is not None:
        event.metadata["area_geojson"] = geometry
        event.lat = 35.1
        event.lon = 14.1
    feature = _public_intel_feature(event)

    assert feature is not None
    assert feature["geometry"] == geometry
    assert feature["properties"]["location_precision"] == precision
    _validator("live-signal-v1.schema.json").validate(feature)


def test_kind_and_lifecycle_are_independent_contract_fields() -> None:
    feature = _public_intel_feature(_public_event())
    assert feature is not None
    feature["properties"]["kind"] = "distress"
    feature["properties"]["incident_lifecycle"] = "resolved"

    _validator("live-signal-v1.schema.json").validate(feature)
    LiveSignalFeature.model_validate(feature)

    feature["properties"]["kind"] = "resolved"
    with pytest.raises(ValidationError):
        LiveSignalFeature.model_validate(feature)


def test_invalid_legacy_public_values_fail_closed(caplog) -> None:
    unknown_policy = _public_event(source_policy="future_unreviewed_transport")
    invalid_timestamp = _public_event()
    invalid_timestamp.timestamp_utc = "not-a-timestamp"

    assert _public_intel_feature(unknown_policy) is None
    assert _public_intel_feature(invalid_timestamp) is None
    assert "future_unreviewed_transport" not in caplog.text
    assert "Reported maritime distress" not in caplog.text


def test_normalized_federated_event_matches_shipped_schema() -> None:
    event = {
        "schema": "seacommons-event-v1",
        "id": "a" * 64,
        "hash": "b" * 64,
        "previous_hash": None,
        "type": "distress_observation",
        "source": "Alarm Phone",
        "node": "collector-1",
        "observed_at": "2026-08-26T10:00:00+00:00",
        "received_at": "2026-08-26T10:00:01+00:00",
        "expires_at_ms": 1_788_000_000_000,
        "visibility": "public",
        "confidence": 0.7,
        "geometry": None,
        "properties": {
            "incident_id": "contract-event-01",
            "incident_lifecycle": "active",
            "location_precision": "unpositioned",
        },
        "source_url": "https://example.org/report",
    }

    _validator("seacommons-event-v1.schema.json").validate(event)

    invalid = {**event, "confidence": 1.2}
    with pytest.raises(JsonSchemaError):
        _validator("seacommons-event-v1.schema.json").validate(invalid)
