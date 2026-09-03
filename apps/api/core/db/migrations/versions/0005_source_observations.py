# SPDX-License-Identifier: AGPL-3.0-or-later
"""source_observations table

Revision ID: 0005_source_observations
Revises: 0004_lossless_event_ids
Create Date: 2026-09-03

docs/fixes.md M1.1: the first durable, lossless, replayable layer of the
canonical data flow (SOURCE INPUT -> RAW OBSERVATION -> ... -> PUBLIC
PROJECTION), written before any classification decision. Idempotent by
(source_name, source_id) -- see core.intel.source_observation. Additive
only; does not touch intel_events or any existing table. Purely additive
and reversible (drop_table undoes exactly what create_table did) -- unlike
0004, downgrade here is safe.

0001_baseline's upgrade() runs `Base.metadata.create_all(checkfirst=True)`
against whatever models currently exist -- on a fresh database this
already creates source_observations (the model is in core.db.models by
the time 0001 runs), since create_all always reflects live metadata, not
the schema as it stood historically. This migration's own create_table
would collide with that on a fresh DB, so it checks first, matching
0001's own checkfirst behaviour; on a real production database (already
past 0001) the table does not exist yet and this creates it normally.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_source_observations"
down_revision = "0004_lossless_event_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "source_observations" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "source_observations",
        sa.Column("observation_id", sa.String(length=64), primary_key=True),
        sa.Column("service", sa.String(length=32), nullable=False),
        sa.Column("lane", sa.String(length=32), nullable=False),
        sa.Column("observation_type", sa.String(length=48), nullable=False),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("source_policy", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=256), nullable=False),
        sa.Column("source_url", sa.String(length=512), server_default=""),
        sa.Column("observed_at", sa.String(length=32), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("raw_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload_ref", sa.Text(), server_default=""),
        sa.Column("lat", sa.Float()),
        sa.Column("lon", sa.Float()),
        sa.Column("location_precision", sa.String(length=32)),
        sa.Column("uncertainty_m", sa.Float()),
        sa.Column("subject_refs", sa.JSON()),
        sa.Column("provenance", sa.JSON()),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime()),
        sa.UniqueConstraint("source_name", "source_id", name="uq_source_observation_delivery_key"),
    )
    op.create_index(
        "ix_source_observations_service", "source_observations", ["service"]
    )
    op.create_index(
        "ix_source_observations_lane", "source_observations", ["lane"]
    )
    op.create_index(
        "ix_source_observations_observation_type", "source_observations", ["observation_type"]
    )
    op.create_index(
        "ix_source_observations_source_name", "source_observations", ["source_name"]
    )
    op.create_index(
        "ix_source_observations_received_at", "source_observations", ["received_at"]
    )
    op.create_index(
        "ix_source_observations_source_ts", "source_observations", ["source_name", "observed_at"]
    )


def downgrade() -> None:
    op.drop_table("source_observations")
