# SPDX-License-Identifier: AGPL-3.0-or-later
"""separate real-world incident status from Live retirement

Revision ID: 0017_incident_status
Revises: 0016_entity_graph
Create Date: 2026-09-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_incident_status"
down_revision = "0016_entity_graph"
branch_labels = None
depends_on = None

_TABLE = "humanitarian_incidents"
_COLUMN = "incident_status"
_INDEX = "ix_humanitarian_incidents_incident_status"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=32), nullable=False, server_default="active"))
    op.execute(sa.text(
        "UPDATE humanitarian_incidents SET incident_status = CASE "
        "WHEN lifecycle = 'resolved' THEN 'resolved' "
        "WHEN lifecycle = 'needs_review' THEN 'needs_review' "
        "WHEN lifecycle = 'archived' THEN 'outcome_unknown' "
        "ELSE 'active' END"
    ))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_TABLE)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_TABLE)
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
