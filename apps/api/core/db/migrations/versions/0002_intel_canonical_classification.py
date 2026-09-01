# SPDX-License-Identifier: AGPL-3.0-or-later
"""intel_events canonical classification fields

Revision ID: 0002_intel_canonical
Revises: 0001_baseline
Create Date: 2026-09-01

docs/fixes.md Phase 2.2 / 3.2: promote the operational classification out of
the free-form ``meta`` JSON into explicit, indexable columns so SQL can
answer "all active humanitarian distress cases" / "all land humanitarian
cases" / "all events with a disputed location" without decoding arbitrary
JSON. Every column is nullable or server-defaulted -- safe on the populated
production table. ``meta`` stays as the provenance / extension envelope; the
app dual-writes both for one release (Phase 2.3).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_intel_canonical"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_COLUMNS = [
    sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("source_timestamp_utc", sa.String(length=32), nullable=True),
    sa.Column("received_at", sa.DateTime(), nullable=True),
    sa.Column("maritime_domain", sa.String(length=32), nullable=True),
    sa.Column("operational_tier", sa.String(length=16), nullable=True),
    sa.Column("humanitarian_case_type", sa.String(length=32), nullable=True),
    sa.Column("incident_lifecycle", sa.String(length=16), nullable=True),
    sa.Column("location_status", sa.String(length=32), nullable=True),
    sa.Column("coordinate_review_status", sa.String(length=40), nullable=True),
    sa.Column("location_uncertainty_m", sa.Float(), nullable=True),
]
_INDEXES = [
    ("ix_intel_events_maritime_domain", "maritime_domain"),
    ("ix_intel_events_operational_tier", "operational_tier"),
    ("ix_intel_events_humanitarian_case_type", "humanitarian_case_type"),
    ("ix_intel_events_incident_lifecycle", "incident_lifecycle"),
]


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("intel_events")}
    with op.batch_alter_table("intel_events") as batch:
        for column in _COLUMNS:
            if column.name not in existing:
                batch.add_column(column)
    for name, column in _INDEXES:
        op.create_index(name, "intel_events", [column], if_not_exists=True)


def downgrade() -> None:
    for name, _column in _INDEXES:
        op.drop_index(name, table_name="intel_events", if_exists=True)
    with op.batch_alter_table("intel_events") as batch:
        for column in reversed(_COLUMNS):
            batch.drop_column(column.name)
