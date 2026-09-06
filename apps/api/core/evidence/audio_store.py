# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass

from core.db.models import AudioEvidenceArtifactDB
from core.evidence.audio_artifact import AudioEvidenceArtifact


@dataclass(frozen=True)
class PersistedAudioArtifact:
    artifact_id: str
    replayed: bool


def persist_audio_artifact(db, artifact: AudioEvidenceArtifact) -> PersistedAudioArtifact:
    """Persist immutable audio metadata/reference; never accepts or stores audio bytes."""
    existing = db.get(AudioEvidenceArtifactDB, artifact.artifact_id)
    if existing is not None:
        return PersistedAudioArtifact(artifact_id=artifact.artifact_id, replayed=True)

    db.add(
        AudioEvidenceArtifactDB(
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            physical_lineage=artifact.physical_lineage,
            receiver_id=artifact.receiver_id,
            frequency_hz=artifact.frequency_hz,
            channel=artifact.channel,
            started_at=artifact.started_at.isoformat(),
            ended_at=artifact.ended_at.isoformat(),
            duration_seconds=artifact.duration_seconds,
            content_sha256=artifact.content_sha256,
            storage_ref=artifact.storage_ref,
            mime_type=artifact.mime_type,
            codec=artifact.codec,
            source_terms=artifact.source_terms,
            retention_policy=artifact.retention_policy,
            source_observation_ids=list(artifact.source_observation_ids),
        )
    )
    db.flush()
    return PersistedAudioArtifact(artifact_id=artifact.artifact_id, replayed=False)
