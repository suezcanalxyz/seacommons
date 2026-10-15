"""Transactional receipts for restart-safe AIS track spool delivery.

Revision ID: 0032_ais_spool_receipts
Revises: 0031_source_obs_lineage_idx
Create Date: 2026-10-15

This migration only creates a small additive table. No track rows, indexes,
evidence, backups or WAL segments are changed. Downgrade is deliberately
non-destructive: removing receipts while replay is possible could duplicate
AIS tracks after a crash, so this table requires an explicit recovery review.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_ais_spool_receipts"
down_revision = "0031_source_obs_lineage_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "vessel_track_ingest_batches" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "vessel_track_ingest_batches",
        sa.Column("batch_id", sa.String(length=64), primary_key=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("committed_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Refusing destructive AIS receipt downgrade. Verify all pending "
        "SQLite spool batches are acknowledged and archived before removal."
    )
