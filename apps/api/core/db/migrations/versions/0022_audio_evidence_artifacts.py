"""add metadata-only audio evidence artifacts

Revision ID: 0022_audio_artifacts
Revises: 0021_maritime_episodes
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_audio_artifacts"
down_revision = "0021_maritime_episodes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "audio_evidence_artifacts" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "audio_evidence_artifacts",
        sa.Column("artifact_id", sa.String(length=64), primary_key=True),
        sa.Column("artifact_type", sa.String(length=16), nullable=False),
        sa.Column("physical_lineage", sa.String(length=128), nullable=False),
        sa.Column("receiver_id", sa.String(length=128), nullable=False),
        sa.Column("frequency_hz", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.String(length=40), nullable=False),
        sa.Column("ended_at", sa.String(length=40), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("codec", sa.String(length=32), nullable=False),
        sa.Column("source_terms", sa.Text(), nullable=False),
        sa.Column("retention_policy", sa.String(length=16), nullable=False),
        sa.Column("source_observation_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audio_evidence_artifacts_physical_lineage", "audio_evidence_artifacts", ["physical_lineage"])
    op.create_index("ix_audio_evidence_artifacts_frequency_hz", "audio_evidence_artifacts", ["frequency_hz"])
    op.create_index("ix_audio_evidence_artifacts_started_at", "audio_evidence_artifacts", ["started_at"])
    op.create_index("ix_audio_evidence_artifacts_content_sha256", "audio_evidence_artifacts", ["content_sha256"])
    op.create_index("ix_audio_evidence_artifacts_retention_policy", "audio_evidence_artifacts", ["retention_policy"])
    op.create_index("ix_audio_artifacts_lineage_start", "audio_evidence_artifacts", ["physical_lineage", "started_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if "audio_evidence_artifacts" not in set(sa.inspect(bind).get_table_names()):
        return
    for name in [
        "ix_audio_artifacts_lineage_start",
        "ix_audio_evidence_artifacts_retention_policy",
        "ix_audio_evidence_artifacts_content_sha256",
        "ix_audio_evidence_artifacts_started_at",
        "ix_audio_evidence_artifacts_frequency_hz",
        "ix_audio_evidence_artifacts_physical_lineage",
    ]:
        op.drop_index(name, table_name="audio_evidence_artifacts")
    op.drop_table("audio_evidence_artifacts")
