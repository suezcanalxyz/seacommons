# SPDX-License-Identifier: AGPL-3.0-or-later
"""source_coverage_events

Revision ID: 0012_source_coverage_events
Revises: 0011_incident_current_drift
Create Date: 2026-09-04

docs/updates.md P1.3: coverage-change integrity -- append-only log of
source coverage changes (added/removed/method_changed/coverage_break),
with per-source incrementing profile_version. New table, no data
migration. Same checkfirst guard as every prior migration in this
series: 0001_baseline's upgrade() runs create_all(checkfirst=True)
against live model metadata, so a fresh database already has this table
(core.db.models.SourceCoverageEventDB) by the time 0001 runs.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_source_coverage_events"
down_revision = "0011_incident_current_drift"
branch_labels = None
depends_on = None

_TABLE = "source_coverage_events"


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text()),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_source_coverage_events_source_name", _TABLE, ["source_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_coverage_events_source_name", table_name=_TABLE)
    op.drop_table(_TABLE)
