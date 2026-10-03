"""Private partner workspace.

Revision ID: 0032_partner_workspace
Revises: 0031_source_obs_lineage_idx
"""
from alembic import op

from core.db.models import WorkspaceRecord, WorkspaceRevision

revision = "0032_partner_workspace"
down_revision = "0031_source_obs_lineage_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    WorkspaceRecord.__table__.create(op.get_bind(), checkfirst=True)
    WorkspaceRevision.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    WorkspaceRevision.__table__.drop(op.get_bind(), checkfirst=True)
    WorkspaceRecord.__table__.drop(op.get_bind(), checkfirst=True)
