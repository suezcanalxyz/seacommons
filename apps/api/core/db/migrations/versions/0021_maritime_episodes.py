"""persist maritime episodes and link v1 hypotheses

Revision ID: 0021_maritime_episodes
Revises: 0020_vessel_baselines
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_maritime_episodes"
down_revision = "0020_vessel_baselines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "maritime_episodes" not in tables:
        op.create_table(
            "maritime_episodes",
            sa.Column("episode_id", sa.String(length=128), primary_key=True),
            sa.Column("episode_family", sa.String(length=64), nullable=False),
            sa.Column("subject_ids", sa.JSON(), nullable=False),
            sa.Column("start_at", sa.DateTime(), nullable=False),
            sa.Column("end_at", sa.DateTime(), nullable=False),
            sa.Column("geometry", sa.JSON()),
            sa.Column("observation_ids", sa.JSON(), nullable=False),
            sa.Column("feature_ids", sa.JSON(), nullable=False),
            sa.Column("independence_groups", sa.JSON(), nullable=False),
            sa.Column("verification_status", sa.String(length=32), nullable=False),
            sa.Column("behaviour_context", sa.JSON(), nullable=False),
            sa.Column("alternative_explanations", sa.JSON(), nullable=False),
            sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("method_version", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_maritime_episodes_episode_family", "maritime_episodes", ["episode_family"])
        op.create_index("ix_maritime_episodes_start_at", "maritime_episodes", ["start_at"])
        op.create_index("ix_maritime_episodes_end_at", "maritime_episodes", ["end_at"])
        op.create_index("ix_maritime_episodes_verification_status", "maritime_episodes", ["verification_status"])
        op.create_index("ix_maritime_episodes_evidence_fingerprint", "maritime_episodes", ["evidence_fingerprint"])
        op.create_index("ix_maritime_episodes_status", "maritime_episodes", ["status"])
        op.create_index("ix_maritime_episodes_family_end", "maritime_episodes", ["episode_family", "end_at"])

    hyp_cols = {c["name"] for c in sa.inspect(bind).get_columns("investigation_hypotheses")}
    if "episode_id" not in hyp_cols:
        op.add_column("investigation_hypotheses", sa.Column("episode_id", sa.String(length=128), nullable=True))
        op.create_index("ix_investigation_hypotheses_episode_id", "investigation_hypotheses", ["episode_id"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "investigation_hypotheses" in tables:
        hyp_cols = {c["name"] for c in sa.inspect(bind).get_columns("investigation_hypotheses")}
        if "episode_id" in hyp_cols:
            op.drop_index("ix_investigation_hypotheses_episode_id", table_name="investigation_hypotheses")
            op.drop_column("investigation_hypotheses", "episode_id")
    if "maritime_episodes" in tables:
        for name in [
            "ix_maritime_episodes_family_end",
            "ix_maritime_episodes_status",
            "ix_maritime_episodes_evidence_fingerprint",
            "ix_maritime_episodes_verification_status",
            "ix_maritime_episodes_end_at",
            "ix_maritime_episodes_start_at",
            "ix_maritime_episodes_episode_family",
        ]:
            op.drop_index(name, table_name="maritime_episodes")
        op.drop_table("maritime_episodes")
