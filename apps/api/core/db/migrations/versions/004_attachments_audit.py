"""004 case attachments and append-only audit log."""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("case_attachments",
        sa.Column("attachment_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False, unique=True),
        sa.Column("filename", sa.String(256), nullable=False), sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_case_attachments_case", "case_attachments", ["case_id"])
    op.create_table("audit_log",
        sa.Column("audit_id", sa.String(36), primary_key=True), sa.Column("actor", sa.String(256), nullable=False),
        sa.Column("action", sa.String(64), nullable=False), sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False), sa.Column("data", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_audit_actor", "audit_log", ["actor"])
    op.create_index("ix_audit_action", "audit_log", ["action"])
    op.create_index("ix_audit_resource", "audit_log", ["resource_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("case_attachments")
