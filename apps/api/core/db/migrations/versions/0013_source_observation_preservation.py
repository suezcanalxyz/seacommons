# SPDX-License-Identifier: AGPL-3.0-or-later
"""source_observations.preservation_status

Revision ID: 0013_source_obs_preservation
Revises: 0012_source_coverage_events
Create Date: 2026-09-04

docs/updates.md Section 6 (Preservation): one additive nullable column
on the existing source_observations table -- core.intel.preservation.
classify_preservation_status's output, computed once at
record_observation() time going forward.

Deterministic backfill for pre-existing rows: preservation_status is a
pure function of (service, has_archive_ref) already stored on every
existing row (service, raw_payload_ref), so this migration also
computes and fills it for rows written before this column existed --
safe and non-destructive (add-only, no existing column touched), unlike
a migration that would have to guess at data it cannot derive.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_source_obs_preservation"
down_revision = "0012_source_coverage_events"
branch_labels = None
depends_on = None

_TABLE = "source_observations"
_COLUMN = "preservation_status"


def upgrade() -> None:
    bind = op.get_bind()
    existing = {col["name"] for col in sa.inspect(bind).get_columns(_TABLE)}
    if _COLUMN in existing:
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(sa.Column(_COLUMN, sa.String(length=32)))

    source_observations = sa.table(
        _TABLE,
        sa.column("observation_id", sa.String),
        sa.column("service", sa.String),
        sa.column("raw_payload_ref", sa.Text),
        sa.column(_COLUMN, sa.String),
    )
    for service, status_if_ref, status_if_no_ref in (
        ("humanitarian", "restricted", "not_applicable"),
        (None, "preserved", "not_applicable"),  # None = "every other service"
    ):
        has_ref = sa.and_(
            source_observations.c.raw_payload_ref.isnot(None),
            source_observations.c.raw_payload_ref != "",
        )
        service_match = (
            source_observations.c.service == service
            if service is not None
            else source_observations.c.service != "humanitarian"
        )
        bind.execute(
            source_observations.update()
            .where(sa.and_(service_match, has_ref))
            .values({_COLUMN: status_if_ref})
        )
        bind.execute(
            source_observations.update()
            .where(sa.and_(service_match, sa.not_(has_ref)))
            .values({_COLUMN: status_if_no_ref})
        )


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column(_COLUMN)
