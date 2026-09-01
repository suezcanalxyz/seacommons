# SPDX-License-Identifier: AGPL-3.0-or-later
"""lossless event identifiers -- widen every semantic event-id column to 64

Revision ID: 0004_lossless_event_ids
Revises: 0003_intel_composite_idx
Create Date: 2026-09-01

docs/prompt.md P0: generated identifiers such as ``spoof:247384100:circular``
overflowed intel_events.id VARCHAR(16), and the linked tables carried the
same identity at 16 / 32 / 36 chars. Widening only -- data preserving, no
table drop. Downgrade is intentionally blocked: shrinking back could
truncate identifiers already stored beyond the old limits.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_lossless_event_ids"
down_revision = "0003_intel_composite_idx"
branch_labels = None
depends_on = None

# (table, column, old length)
_WIDEN = [
    ("intel_events", "id", 16),
    ("alert_events", "event_id", 36),
    ("anomaly_events", "event_id", 36),
    ("forensic_events", "event_id", 36),
    ("drift_results", "event_id", 36),
    ("case_intel_events", "event_id", 32),
]
_NEW_LEN = 64


def upgrade() -> None:
    for table, column, old_len in _WIDEN:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=sa.String(length=old_len),
                type_=sa.String(length=_NEW_LEN),
                existing_nullable=False,
            )


def downgrade() -> None:
    raise RuntimeError(
        "0004_lossless_event_ids is widening-only. Narrowing intel event "
        "identifier columns back to 16/32/36 would truncate identifiers "
        "already stored at their full width. Restore from a backup instead."
    )
