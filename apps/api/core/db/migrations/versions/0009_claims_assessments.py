# SPDX-License-Identifier: AGPL-3.0-or-later
"""claims / assessments tables

Revision ID: 0009_claims_assessments
Revises: 0008_humanitarian_incidents
Create Date: 2026-09-04

docs/updates.md P0.4: "important facts become claims, not mutable scalar
truth" -- claims are append-only per (incident, claim_type, observation);
assessments are the selected/bounded value with explicit supporting/
contradicting claim references. Purely additive and reversible.

0001_baseline's upgrade() runs `Base.metadata.create_all(checkfirst=True)`
against whatever models currently exist -- on a fresh database this
already creates both tables (the models are in core.db.models by the
time 0001 runs), same reasoning as every prior 000N migration in this
series. This migration's own create_table checks first for the same
reason.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_claims_assessments"
down_revision = "0008_humanitarian_incidents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "claims" not in existing:
        op.create_table(
            "claims",
            sa.Column("claim_id", sa.String(length=96), primary_key=True),
            sa.Column("incident_id", sa.String(length=64), nullable=False),
            sa.Column("claim_type", sa.String(length=32), nullable=False),
            sa.Column("value", sa.JSON(), nullable=False),
            sa.Column("observation_id", sa.String(length=64), nullable=False),
            sa.Column("source_id", sa.String(length=64)),
            sa.Column("claimed_at", sa.String(length=32)),
            sa.Column("observed_at", sa.String(length=32)),
            sa.Column("extraction_method", sa.String(length=64), nullable=False),
            sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="unverified"),
            sa.Column("supersedes_id", sa.String(length=96)),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_claims_incident_id", "claims", ["incident_id"])
        op.create_index("ix_claims_claim_type", "claims", ["claim_type"])

    if "assessments" not in existing:
        op.create_table(
            "assessments",
            sa.Column("assessment_id", sa.String(length=96), primary_key=True),
            sa.Column("incident_id", sa.String(length=64), nullable=False),
            sa.Column("field_type", sa.String(length=32), nullable=False),
            sa.Column("value", sa.JSON()),
            sa.Column("supporting_claim_ids", sa.JSON()),
            sa.Column("contradicting_claim_ids", sa.JSON()),
            sa.Column("method_version", sa.String(length=64), nullable=False),
            sa.Column("confidence", sa.Float()),
            sa.Column("review_state", sa.String(length=32), nullable=False, server_default="unreviewed"),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )
        op.create_index("ix_assessments_incident_id", "assessments", ["incident_id"])


def downgrade() -> None:
    op.drop_table("assessments")
    op.drop_table("claims")
