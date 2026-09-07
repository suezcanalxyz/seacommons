"""persist decoded radio to AIS associations

Revision ID: 0026_radio_ais_associations
Revises: 0025_radio_bursts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_radio_ais_associations"
down_revision = "0025_radio_bursts"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "radio_ais_associations" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "radio_ais_associations",
        sa.Column("observation_id", sa.String(64), primary_key=True),
        sa.Column("mmsi", sa.String(16), nullable=False),
        sa.Column("match_status", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("distance_km", sa.Float()),
        sa.Column("ais_observed_at", sa.String(40)),
        sa.Column("episode_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_radio_ais_associations_mmsi", "radio_ais_associations", ["mmsi"])
    op.create_index("ix_radio_ais_associations_match_status", "radio_ais_associations", ["match_status"])


def downgrade():
    bind = op.get_bind()
    if "radio_ais_associations" not in set(sa.inspect(bind).get_table_names()):
        return
    op.drop_index("ix_radio_ais_associations_match_status", table_name="radio_ais_associations")
    op.drop_index("ix_radio_ais_associations_mmsi", table_name="radio_ais_associations")
    op.drop_table("radio_ais_associations")
