# SPDX-License-Identifier: AGPL-3.0-or-later
"""investigation_hypotheses table

Revision ID: 0007_investigation_hypotheses
Revises: 0006_drift_origin_evidence
Create Date: 2026-09-04

docs/fixes.md M6/M14.3: persistence for core.intel.hypothesis.
InvestigationHypothesis, the evidence-gated Maritime Intelligence
lifecycle engine. Purely additive and reversible (drop_table undoes
exactly what create_table did) -- does not touch any existing table.

0001_baseline's upgrade() runs `Base.metadata.create_all(checkfirst=True)`
against whatever models currently exist -- on a fresh database this
already creates investigation_hypotheses (the model is in core.db.models
by the time 0001 runs), same reasoning as 0005_source_observations. This
migration's own create_table checks first for the same reason.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_investigation_hypotheses"
down_revision = "0006_drift_origin_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "investigation_hypotheses" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "investigation_hypotheses",
        sa.Column("hypothesis_id", sa.String(length=128), primary_key=True),
        sa.Column("hypothesis_type", sa.String(length=64), nullable=False),
        sa.Column("subject_ids", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="candidate"),
        sa.Column("reason_codes", sa.JSON()),
        sa.Column("counter_indicators", sa.JSON()),
        sa.Column("evidence_links", sa.JSON()),
        sa.Column("evidence_stage", sa.String(length=32), nullable=False, server_default="observed"),
        sa.Column(
            "has_unresolved_blocking_identity_conflict",
            sa.Boolean(), nullable=False, server_default=sa.false(),
        ),
        sa.Column("allegation_shaped_wording", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("explicit_review_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("audit_history", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index(
        "ix_investigation_hypotheses_hypothesis_type",
        "investigation_hypotheses", ["hypothesis_type"],
    )
    op.create_index(
        "ix_investigation_hypotheses_state", "investigation_hypotheses", ["state"],
    )
    op.create_index(
        "ix_investigation_hypotheses_type_state",
        "investigation_hypotheses", ["hypothesis_type", "state"],
    )


def downgrade() -> None:
    op.drop_table("investigation_hypotheses")
