"""persist closed RF bursts

Revision ID: 0025_radio_bursts
Revises: 0024_receiver_catalog
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
revision = "0025_radio_bursts"
down_revision = "0024_receiver_catalog"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if "radio_bursts" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "radio_bursts",
        sa.Column("burst_id", sa.String(64), primary_key=True),
        sa.Column("physical_lineage", sa.String(128), nullable=False),
        sa.Column("frequency_hz", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("peak_signal_db", sa.Float(), nullable=False),
        sa.Column("mean_signal_db", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_radio_bursts_physical_lineage", "radio_bursts", ["physical_lineage"])
    op.create_index("ix_radio_bursts_frequency_hz", "radio_bursts", ["frequency_hz"])
    op.create_index("ix_radio_bursts_started_at", "radio_bursts", ["started_at"])
    op.create_table(
        "radio_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("frequency_hz", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=False),
        sa.Column("independent_receivers", sa.Integer(), nullable=False),
        sa.Column("physical_lineages", sa.JSON(), nullable=False),
        sa.Column("burst_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_radio_events_frequency_hz", "radio_events", ["frequency_hz"])
    op.create_index("ix_radio_events_started_at", "radio_events", ["started_at"])

def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "radio_events" in tables:
        op.drop_index("ix_radio_events_started_at", table_name="radio_events")
        op.drop_index("ix_radio_events_frequency_hz", table_name="radio_events")
        op.drop_table("radio_events")
    if "radio_bursts" not in tables:
        return
    for name in ["ix_radio_bursts_started_at", "ix_radio_bursts_frequency_hz", "ix_radio_bursts_physical_lineage"]:
        op.drop_index(name, table_name="radio_bursts")
    op.drop_table("radio_bursts")
