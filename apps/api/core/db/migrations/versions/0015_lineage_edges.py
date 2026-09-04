# SPDX-License-Identifier: AGPL-3.0-or-later
"""lineage_edges

Revision ID: 0015_lineage_edges
Revises: 0014_correlation_decisions
Create Date: 2026-09-04

docs/updates.md P2.2: circular-reporting lineage -- append-only table of
detected derivation/quotation edges between SourceObservations. New
table, no data migration. Same checkfirst guard as every prior
migration in this series: 0001_baseline's upgrade() runs
create_all(checkfirst=True) against live model metadata, so a fresh
database already has this table (core.db.models.LineageEdgeDB) by the
time 0001 runs.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_lineage_edges"
down_revision = "0014_correlation_decisions"
branch_labels = None
depends_on = None

_TABLE = "lineage_edges"


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("from_observation_id", sa.String(length=64), nullable=False),
        sa.Column("to_observation_id", sa.String(length=64), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("method_version", sa.String(length=64), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_lineage_edges_from_observation_id", _TABLE, ["from_observation_id"])
    op.create_index("ix_lineage_edges_to_observation_id", _TABLE, ["to_observation_id"])


def downgrade() -> None:
    op.drop_index("ix_lineage_edges_to_observation_id", table_name=_TABLE)
    op.drop_index("ix_lineage_edges_from_observation_id", table_name=_TABLE)
    op.drop_table(_TABLE)
