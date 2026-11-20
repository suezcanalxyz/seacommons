# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


SCHEMA = json.loads(
    (Path(__file__).parents[1] / "docs/contracts/evidence-envelope-v1.schema.json")
    .read_text(encoding="utf-8")
)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def _record() -> dict:
    return {
        "schema_version": "evidence-envelope-v1",
        "source_id": "aisstream:249207000:2026-11-18T10:21:33Z",
        "source_type": "terrestrial_ais",
        "provider": "AISStream",
        "source_url": "https://aisstream.io/",
        "raw_message_reference": "object://raw/sha256/example",
        "raw_payload_sha256": "a" * 64,
        "observed_at": "2026-11-18T10:21:33Z",
        "received_at": "2026-11-18T10:21:34Z",
        "ingested_at": "2026-11-18T10:21:35Z",
        "processed_at": "2026-11-18T10:21:36Z",
        "published_at": None,
        "location": {"type": "Point", "coordinates": [15.18848, 37.20875]},
        "location_uncertainty": {"radius_m": 1000, "basis": "provider_unspecified"},
        "identity_confidence": 0.7,
        "independent_source_count": 1,
        "source_independence_group": "aisstream_upstream_unknown",
        "method_version": "adjacent_fix_geodesic_v1",
        "evidence_level": "observation",
        "limitations": ["Provider upstream lineage is not established."],
        "processing_version": "git:714df4c0",
        "lineage_parent_ids": [],
        "collection_state": "received",
    }


def test_evidence_envelope_accepts_explicit_observation_provenance():
    VALIDATOR.validate(_record())


def test_evidence_envelope_rejects_missing_lineage_and_unknown_levels():
    record = _record()
    del record["raw_message_reference"]
    record["evidence_level"] = "confirmed_truth"

    with pytest.raises(Exception):
        VALIDATOR.validate(record)
