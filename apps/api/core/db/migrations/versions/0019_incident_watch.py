# SPDX-License-Identifier: AGPL-3.0-or-later
"""incident watch persistence

Revision ID: 0019_incident_watch
Revises: 0018_satellite_observations
Create Date: 2026-09-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_incident_watch"
down_revision = "0018_satellite_observations"
branch_labels = None
depends_on = None

_TABLE = "incident_watches"


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("watch_id", sa.String(length=64), primary_key=True),
        sa.Column("incident_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("lifecycle_snapshot", sa.String(length=32), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_run_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_at", sa.DateTime()),
        sa.Column("last_success_at", sa.DateTime()),
        sa.Column("last_error_at", sa.DateTime()),
        sa.Column("last_error_class", sa.String(length=64)),
        sa.Column("consecutive_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("query_fingerprint", sa.String(length=64)),
        sa.Column("lease_owner", sa.String(length=128)),
        sa.Column("lease_until", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime()),
        sa.UniqueConstraint("incident_id", name="uq_incident_watch_incident"),
    )
    op.create_index("ix_incident_watches_status", _TABLE, ["status"])
    op.create_index("ix_incident_watches_priority", _TABLE, ["priority"])
    op.create_index("ix_incident_watches_next_run_at", _TABLE, ["next_run_at"])
    op.create_index("ix_incident_watches_lease_until", _TABLE, ["lease_until"])
    op.create_index("ix_incident_watches_due", _TABLE, ["status", "next_run_at", "priority"])


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        return
    op.drop_index("ix_incident_watches_due", table_name=_TABLE)
    op.drop_index("ix_incident_watches_lease_until", table_name=_TABLE)
    op.drop_index("ix_incident_watches_next_run_at", table_name=_TABLE)
    op.drop_index("ix_incident_watches_priority", table_name=_TABLE)
    op.drop_index("ix_incident_watches_status", table_name=_TABLE)
    op.drop_table(_TABLE)
