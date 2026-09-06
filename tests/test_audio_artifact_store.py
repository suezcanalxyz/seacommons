from __future__ import annotations

from datetime import datetime, timezone


def _artifact(**overrides):
    from core.evidence.audio_artifact import AudioEvidenceArtifact

    values = {
        "physical_lineage": "med_rx_01",
        "receiver_id": "openwebrx_med_rx",
        "frequency_hz": 2_182_000,
        "channel": "2182-khz",
        "started_at": datetime(2026, 9, 6, 20, 10, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 9, 6, 20, 10, 30, tzinfo=timezone.utc),
        "content_sha256": "b" * 64,
        "storage_ref": "object://restricted-audio/clip-002.flac",
        "mime_type": "audio/flac",
        "codec": "flac",
        "source_terms": "operator-permission",
        "retention_policy": "7d",
        "source_observation_ids": ("obs:radio:2", "obs:dsc:2"),
    }
    values.update(overrides)
    return AudioEvidenceArtifact(**values)


def test_persist_audio_artifact_is_idempotent_by_artifact_id():
    from core.db.models import AudioEvidenceArtifactDB
    from core.db.session import session_scope
    from core.evidence.audio_store import persist_audio_artifact

    artifact = _artifact()
    with session_scope() as db:
        first = persist_audio_artifact(db, artifact)
        second = persist_audio_artifact(db, artifact)
        assert first.replayed is False
        assert second.replayed is True
        assert first.artifact_id == second.artifact_id == artifact.artifact_id

    with session_scope() as db:
        rows = db.query(AudioEvidenceArtifactDB).filter_by(artifact_id=artifact.artifact_id).all()
        assert len(rows) == 1


def test_store_persists_metadata_reference_and_hash_without_audio_bytes_or_transcript():
    from core.db.models import AudioEvidenceArtifactDB
    from core.db.session import session_scope
    from core.evidence.audio_store import persist_audio_artifact

    artifact = _artifact(content_sha256="c" * 64, storage_ref="object://restricted-audio/clip-003.flac")
    with session_scope() as db:
        result = persist_audio_artifact(db, artifact)
        row = db.get(AudioEvidenceArtifactDB, result.artifact_id)
        columns = set(AudioEvidenceArtifactDB.__table__.columns.keys())
        snapshot = {
            "content_sha256": row.content_sha256,
            "storage_ref": row.storage_ref,
            "physical_lineage": row.physical_lineage,
            "receiver_id": row.receiver_id,
            "retention_policy": row.retention_policy,
            "source_observation_ids": tuple(row.source_observation_ids),
        }

    assert snapshot["content_sha256"] == "c" * 64
    assert snapshot["storage_ref"] == "object://restricted-audio/clip-003.flac"
    assert snapshot["physical_lineage"] == "med_rx_01"
    assert snapshot["receiver_id"] == "openwebrx_med_rx"
    assert snapshot["retention_policy"] == "7d"
    assert snapshot["source_observation_ids"] == ("obs:radio:2", "obs:dsc:2")
    for forbidden in ("audio_bytes", "blob", "waveform", "iq", "transcript", "humanitarian", "lifecycle", "publication", "model_output"):
        assert forbidden not in columns


def test_same_content_different_physical_lineage_does_not_fake_same_artifact_identity():
    one = _artifact(physical_lineage="rx-one", content_sha256="d" * 64)
    two = _artifact(physical_lineage="rx-two", content_sha256="d" * 64)
    assert one.artifact_id != two.artifact_id


def test_migration_head_contains_audio_artifact_table_metadata_only():
    import sqlalchemy as sa
    from core.db.models import AudioEvidenceArtifactDB

    columns = set(AudioEvidenceArtifactDB.__table__.columns.keys())
    assert {"artifact_id", "content_sha256", "storage_ref", "retention_policy", "source_observation_ids"} <= columns
    assert all(not isinstance(column.type, sa.LargeBinary) for column in AudioEvidenceArtifactDB.__table__.columns)
