# SPDX-License-Identifier: AGPL-3.0-or-later
"""provider-neutral satellite observations

Revision ID: 0018_satellite_observations
Revises: 0017_incident_status
Create Date: 2026-09-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_satellite_observations"
down_revision = "0017_incident_status"
branch_labels = None
depends_on = None

_TABLE = "satellite_observations"


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("observation_id", sa.String(length=64), primary_key=True),
        sa.Column("incident_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=48), nullable=False),
        sa.Column("mission", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=256), nullable=False),
        sa.Column("acquisition_time", sa.String(length=32), nullable=False),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
        sa.Column("footprint", sa.JSON()),
        sa.Column("bbox", sa.JSON()),
        sa.Column("sensor_type", sa.String(length=32), nullable=False),
        sa.Column("temporal_relation", sa.String(length=16), nullable=False),
        sa.Column("temporal_delta_s", sa.Float(), nullable=False, server_default="0"),
        sa.Column("asset_ref", sa.Text()),
        sa.Column("source_url", sa.Text()),
        sa.Column("provenance", sa.JSON()),
        sa.Column("resolution_m", sa.Float()),
        sa.Column("cloud_cover", sa.Float()),
        sa.Column("polarisation", sa.JSON()),
        sa.Column("evidence_status", sa.String(length=32), nullable=False, server_default="contextual"),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_satellite_observations_incident_id", _TABLE, ["incident_id"])
    op.create_index("ix_satellite_observations_provider", _TABLE, ["provider"])
    op.create_index("ix_satellite_observations_acquisition_time", _TABLE, ["acquisition_time"])
    op.create_index(
        "ix_satellite_observations_incident_time", _TABLE,
        ["incident_id", "acquisition_time"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        return
    op.drop_index("ix_satellite_observations_incident_time", table_name=_TABLE)
    op.drop_index("ix_satellite_observations_acquisition_time", table_name=_TABLE)
    op.drop_index("ix_satellite_observations_provider", table_name=_TABLE)
    op.drop_index("ix_satellite_observations_incident_id", table_name=_TABLE)
    op.drop_table(_TABLE)
