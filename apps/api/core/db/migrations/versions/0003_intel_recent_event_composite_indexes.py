# SPDX-License-Identifier: AGPL-3.0-or-later
"""intel_events recent-event composite indexes

Revision ID: 0003_intel_composite_idx
Revises: 0002_intel_canonical
Create Date: 2026-09-01

docs/fixes.md F-14 / Phase 2.2: every hot read of intel_events
(store.persisted_events, the edge publisher's collect()) filters a recent
timestamp_utc window by ``source`` or ``type`` and sorts by
``timestamp_utc`` descending. A composite (source, timestamp_utc) /
(type, timestamp_utc) index serves the filter and the sort together. The
single-column indexes stay -- do not drop them until real query plans say so.
"""
from __future__ import annotations

from alembic import op

revision = "0003_intel_composite_idx"
down_revision = "0002_intel_canonical"
branch_labels = None
depends_on = None

_INDEXES = [
    ("ix_intel_events_source_ts", ["source", "timestamp_utc"]),
    ("ix_intel_events_type_ts", ["type", "timestamp_utc"]),
]


def upgrade() -> None:
    for name, columns in _INDEXES:
        op.create_index(name, "intel_events", columns, if_not_exists=True)


def downgrade() -> None:
    for name, _columns in _INDEXES:
        op.drop_index(name, table_name="intel_events", if_exists=True)
