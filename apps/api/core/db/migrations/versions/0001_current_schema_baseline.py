# SPDX-License-Identifier: AGPL-3.0-or-later
"""current schema baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-01

docs/fixes.md Phase 2.2: the non-destructive entry point for Alembic on a
database that already exists.

- Fresh database (tests, a new deploy): ``upgrade()`` builds the entire
  current schema from the live model metadata.
- Existing production database: run ``alembic stamp 0001_baseline`` once,
  after checking schema equivalence, and this revision never executes -- the
  real schema evolution starts at 0002.

``_ensure_indexes`` / ``_ensure_additive_columns`` stay in place for one
compatibility release; retire the runtime DDL once every environment is at
migration head.
"""
from __future__ import annotations

from alembic import op

from core.db.models import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # checkfirst=True: safe to run against a database that already has some or
    # all of these tables (create_all never drops or alters).
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
