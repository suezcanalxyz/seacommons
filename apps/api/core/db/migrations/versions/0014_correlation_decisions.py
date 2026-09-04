# SPDX-License-Identifier: AGPL-3.0-or-later
"""correlation_decisions

Revision ID: 0014_correlation_decisions
Revises: 0013_source_obs_preservation
Create Date: 2026-09-04

docs/updates.md P2.1: CorrelationDecision -- append-only table of
candidate incident pairings surfaced for review. New table, no data
migration. Same checkfirst guard as every prior migration in this
series: 0001_baseline's upgrade() runs create_all(checkfirst=True)
against live model metadata, so a fresh database already has this
table (core.db.models.CorrelationDecisionDB) by the time 0001 runs.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_correlation_decisions"
down_revision = "0013_source_obs_preservation"
branch_labels = None
depends_on = None

_TABLE = "correlation_decisions"


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("observation_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_incident_id", sa.String(length=64)),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("supporting_features", sa.JSON()),
        sa.Column("contradicting_features", sa.JSON()),
        sa.Column("source_independence_result", sa.Boolean()),
        sa.Column("method_version", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("review_state", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_correlation_decisions_observation_id", _TABLE, ["observation_id"])
    op.create_index("ix_correlation_decisions_candidate_incident_id", _TABLE, ["candidate_incident_id"])


def downgrade() -> None:
    op.drop_index("ix_correlation_decisions_candidate_incident_id", table_name=_TABLE)
    op.drop_index("ix_correlation_decisions_observation_id", table_name=_TABLE)
    op.drop_table(_TABLE)
