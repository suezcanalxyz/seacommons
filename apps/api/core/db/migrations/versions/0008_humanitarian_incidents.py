# SPDX-License-Identifier: AGPL-3.0-or-later
"""humanitarian_incidents table

Revision ID: 0008_humanitarian_incidents
Revises: 0007_investigation_hypotheses
Create Date: 2026-09-04

docs/updates.md P0.3: the canonical HumanitarianIncident persistence
layer -- "make HumanitarianIncident a stable incident object independent
of any one source post." Purely additive and reversible (drop_table
undoes exactly what create_table did) -- does not touch any existing
table.

0001_baseline's upgrade() runs `Base.metadata.create_all(checkfirst=True)`
against whatever models currently exist -- on a fresh database this
already creates humanitarian_incidents (the model is in core.db.models
by the time 0001 runs), same reasoning as 0005_source_observations and
0007_investigation_hypotheses. This migration's own create_table checks
first for the same reason.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_humanitarian_incidents"
down_revision = "0007_investigation_hypotheses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "humanitarian_incidents" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "humanitarian_incidents",
        sa.Column("incident_id", sa.String(length=64), primary_key=True),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("case_type", sa.String(length=64)),
        sa.Column("reported_at", sa.String(length=32)),
        sa.Column("last_update_at", sa.String(length=32)),
        sa.Column("state_changed_at", sa.DateTime()),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("archived_at", sa.DateTime()),
        sa.Column("source_observation_ids", sa.JSON()),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index(
        "ix_humanitarian_incidents_lifecycle", "humanitarian_incidents", ["lifecycle"],
    )


def downgrade() -> None:
    op.drop_table("humanitarian_incidents")
