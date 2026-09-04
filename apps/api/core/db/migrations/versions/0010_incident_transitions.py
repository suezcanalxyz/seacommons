# SPDX-License-Identifier: AGPL-3.0-or-later
"""incident_transitions table

Revision ID: 0010_incident_transitions
Revises: 0009_claims_assessments
Create Date: 2026-09-04

docs/updates.md P0.5: "every transition is data" -- an append-only audit
log of HumanitarianIncident lifecycle transitions, never a silent state
change. Purely additive and reversible.

0001_baseline's upgrade() runs `Base.metadata.create_all(checkfirst=True)`
against whatever models currently exist -- on a fresh database this
already creates incident_transitions (the model is in core.db.models by
the time 0001 runs), same reasoning as every prior 000N migration in
this series. This migration's own create_table checks first for the
same reason.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_incident_transitions"
down_revision = "0009_claims_assessments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "incident_transitions" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "incident_transitions",
        sa.Column("transition_id", sa.String(length=96), primary_key=True),
        sa.Column("incident_id", sa.String(length=64), nullable=False),
        sa.Column("from_state", sa.String(length=32)),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("transition_at", sa.DateTime(), nullable=False),
        sa.Column("effective_at", sa.String(length=32)),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("supporting_observation_ids", sa.JSON()),
        sa.Column("contradicting_observation_ids", sa.JSON()),
        sa.Column("method_version", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("review_decision_id", sa.String(length=96)),
    )
    op.create_index("ix_incident_transitions_incident_id", "incident_transitions", ["incident_id"])


def downgrade() -> None:
    op.drop_table("incident_transitions")
