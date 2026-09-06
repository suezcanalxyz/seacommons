# SPDX-License-Identifier: AGPL-3.0-or-later
"""vessel behavioural baseline persistence

Revision ID: 0020_vessel_behavioural_baselines
Revises: 0019_incident_watch
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_vessel_behavioural_baselines"
down_revision = "0019_incident_watch"
branch_labels = None
depends_on = None
_TABLE = "vessel_behavioural_baselines"


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("baseline_id", sa.String(length=64), primary_key=True),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("primary_mmsi", sa.String(length=16), nullable=False),
        sa.Column("primary_imo", sa.String(length=16)),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("history_days", sa.Float(), nullable=False),
        sa.Column("route_model", sa.JSON(), nullable=False),
        sa.Column("speed_model", sa.JSON(), nullable=False),
        sa.Column("port_model", sa.JSON(), nullable=False),
        sa.Column("silence_model", sa.JSON(), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("method_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("subject_id", "window_start", "window_end", "method_version", "evidence_fingerprint", name="uq_vessel_baseline_evidence_window"),
    )
    op.create_index("ix_vessel_behavioural_baselines_subject_id", _TABLE, ["subject_id"])
    op.create_index("ix_vessel_behavioural_baselines_primary_mmsi", _TABLE, ["primary_mmsi"])
    op.create_index("ix_vessel_behavioural_baselines_primary_imo", _TABLE, ["primary_imo"])
    op.create_index("ix_vessel_behavioural_baselines_window_end", _TABLE, ["window_end"])
    op.create_index("ix_vessel_behavioural_baselines_evidence_fingerprint", _TABLE, ["evidence_fingerprint"])
    op.create_index("ix_vessel_baselines_mmsi_window", _TABLE, ["primary_mmsi", "window_end"])


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        return
    for name in [
        "ix_vessel_baselines_mmsi_window",
        "ix_vessel_behavioural_baselines_evidence_fingerprint",
        "ix_vessel_behavioural_baselines_window_end",
        "ix_vessel_behavioural_baselines_primary_imo",
        "ix_vessel_behavioural_baselines_primary_mmsi",
        "ix_vessel_behavioural_baselines_subject_id",
    ]:
        op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)
