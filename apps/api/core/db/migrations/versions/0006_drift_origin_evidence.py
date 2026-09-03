# SPDX-License-Identifier: AGPL-3.0-or-later
"""drift_results.origin_evidence_id / model_version

Revision ID: 0006_drift_origin_evidence
Revises: 0005_source_observations
Create Date: 2026-09-03

docs/fixes.md M3 rule: "Drift result always records origin evidence ID and
model version." Two nullable columns on the existing drift_results table --
additive only, no data migration, existing rows simply read back with both
columns NULL (a pre-M3 job legitimately has no origin evidence id to
backfill). Dedicated columns rather than folding into metadata_json:
core.db.store.complete_drift_job() replaces metadata_json wholesale with
the engine's own result.metadata, which would silently wipe a value stored
there instead.

Same checkfirst guard as 0005_source_observations: 0001_baseline's
upgrade() runs create_all(checkfirst=True) against live model metadata, so
a fresh database already has both columns (core.db.models.DriftResultDB)
by the time 0001 runs; this migration's own add_column would collide with
that on a fresh DB.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_drift_origin_evidence"
down_revision = "0005_source_observations"
branch_labels = None
depends_on = None

_TABLE = "drift_results"
_COLUMNS = ("origin_evidence_id", "model_version")


def upgrade() -> None:
    bind = op.get_bind()
    existing = {col["name"] for col in sa.inspect(bind).get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        for column in _COLUMNS:
            if column in existing:
                continue
            batch.add_column(sa.Column(column, sa.String(length=64)))


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        for column in _COLUMNS:
            batch.drop_column(column)
