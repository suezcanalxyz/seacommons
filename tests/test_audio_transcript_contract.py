from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone

import pytest


def _transcript(**overrides):
    from core.evidence.audio_transcript import DerivedAudioTranscript

    values = {
        "artifact_id": "audio:abc123",
        "artifact_sha256": "e" * 64,
        "text": "MAYDAY MAYDAY vessel requires assistance",
        "language": "en",
        "engine": "local-stt",
        "model": "whisper-compatible",
        "model_version": "1.0",
        "created_at": datetime(2026, 9, 6, 20, 30, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return DerivedAudioTranscript(**values)


def test_transcript_is_frozen_derived_and_deterministic():
    first = _transcript()
    second = _transcript()
    assert first.transcript_id == second.transcript_id
    assert first.derived is True
    assert first.canonical_authority is False
    with pytest.raises(FrozenInstanceError):
        first.text = "changed"  # type: ignore[misc]


def test_transcript_contract_has_no_domain_decision_authority_fields():
    names = {field.name for field in fields(type(_transcript()))}
    for forbidden in ("humanitarian", "lifecycle", "publication", "decision", "incident_status", "confidence_override"):
        assert forbidden not in names


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"artifact_id": ""}, "artifact_id"),
        ({"artifact_sha256": "bad"}, "sha256"),
        ({"text": ""}, "text"),
        ({"engine": ""}, "engine"),
        ({"model": ""}, "model"),
        ({"model_version": ""}, "model_version"),
    ],
)
def test_required_provenance_fields_fail_closed(overrides, match):
    with pytest.raises(ValueError, match=match):
        _transcript(**overrides)


def test_transcript_text_is_bounded_and_timestamp_must_be_aware():
    transcript = _transcript(text="x" * 25000)
    assert len(transcript.text) == 20000
    with pytest.raises(ValueError, match="timezone"):
        _transcript(created_at=datetime(2026, 9, 6, 20, 30))


def test_different_model_version_or_text_produces_distinct_derived_identity():
    base = _transcript()
    assert _transcript(model_version="1.1").transcript_id != base.transcript_id
    assert _transcript(text="different").transcript_id != base.transcript_id
