# SPDX-License-Identifier: AGPL-3.0-or-later
"""humanitarian_incidents.current_drift_id

Revision ID: 0011_incident_current_drift
Revises: 0010_incident_transitions
Create Date: 2026-09-04

docs/updates.md P0.7: Drift ownership -- one nullable column on the
existing humanitarian_incidents table. Additive only, no data migration;
existing rows simply read back with current_drift_id NULL (no incident
predating this packet has ever had an owned Drift recorded). Same
checkfirst guard as every prior migration in this series:
0001_baseline's upgrade() runs create_all(checkfirst=True) against live
model metadata, so a fresh database already has this column
(core.db.models.HumanitarianIncidentDB) by the time 0001 runs; this
migration's own add_column would collide with that on a fresh DB.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_incident_current_drift"
down_revision = "0010_incident_transitions"
branch_labels = None
depends_on = None

_TABLE = "humanitarian_incidents"
_COLUMN = "current_drift_id"


def upgrade() -> None:
    bind = op.get_bind()
    existing = {col["name"] for col in sa.inspect(bind).get_columns(_TABLE)}
    if _COLUMN in existing:
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(sa.Column(_COLUMN, sa.String(length=36)))


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column(_COLUMN)
