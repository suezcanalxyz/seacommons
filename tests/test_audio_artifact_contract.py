from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone

import pytest


def _artifact(**overrides):
    from core.evidence.audio_artifact import AudioEvidenceArtifact

    values = {
        "physical_lineage": "med_rx_01",
        "receiver_id": "openwebrx_med_rx",
        "frequency_hz": 2_182_000,
        "channel": "2182-khz",
        "started_at": datetime(2026, 9, 6, 20, 0, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 9, 6, 20, 0, 30, tzinfo=timezone.utc),
        "content_sha256": "a" * 64,
        "storage_ref": "object://restricted-audio/clip-001.flac",
        "mime_type": "audio/flac",
        "codec": "flac",
        "source_terms": "operator-permission",
        "retention_policy": "7d",
        "source_observation_ids": ("obs:radio:1",),
    }
    values.update(overrides)
    return AudioEvidenceArtifact(**values)


def test_audio_artifact_is_frozen_normalized_and_deterministic():
    first = _artifact(physical_lineage="Med RX 01", receiver_id="OpenWebRX Med RX")
    second = _artifact(physical_lineage="med_rx_01", receiver_id="openwebrx_med_rx")
    assert first.artifact_type == "audio"
    assert first.physical_lineage == "med_rx_01"
    assert first.receiver_id == "openwebrx_med_rx"
    assert first.artifact_id == second.artifact_id
    assert first.duration_seconds == 30.0
    with pytest.raises(FrozenInstanceError):
        first.codec = "wav"  # type: ignore[misc]


def test_artifact_contract_has_no_truth_or_transcript_authority_fields():
    names = {field.name for field in fields(type(_artifact()))}
    for forbidden in ("humanitarian", "lifecycle", "publication", "transcript", "claim", "model_output", "decision"):
        assert forbidden not in names


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"content_sha256": "bad"}, "sha256"),
        ({"storage_ref": ""}, "storage_ref"),
        ({"source_terms": ""}, "source_terms"),
        ({"retention_policy": "forever"}, "retention"),
        ({"frequency_hz": 0}, "frequency"),
        ({"mime_type": "application/octet-stream"}, "mime"),
        ({"codec": ""}, "codec"),
    ],
)
def test_invalid_hash_storage_terms_retention_frequency_and_media_fail_closed(overrides, match):
    with pytest.raises(ValueError, match=match):
        _artifact(**overrides)


def test_time_window_is_timezone_aware_positive_and_bounded():
    start = datetime(2026, 9, 6, 20, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="timezone"):
        _artifact(started_at=start.replace(tzinfo=None))
    with pytest.raises(ValueError, match="ended_at"):
        _artifact(ended_at=start)
    with pytest.raises(ValueError, match="duration"):
        _artifact(ended_at=start + timedelta(minutes=6))


def test_source_observation_links_are_bounded_deduplicated_and_required():
    artifact = _artifact(source_observation_ids=("obs:radio:1", "obs:radio:1", "obs:radio:2"))
    assert artifact.source_observation_ids == ("obs:radio:1", "obs:radio:2")
    with pytest.raises(ValueError, match="source_observation"):
        _artifact(source_observation_ids=())
    with pytest.raises(ValueError, match="source_observation"):
        _artifact(source_observation_ids=tuple(f"obs:{i}" for i in range(33)))
