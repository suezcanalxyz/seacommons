"""007 organizations, case access and retention governance."""
from alembic import op
import sqlalchemy as sa
revision = "007"; down_revision = "006"; branch_labels = None; depends_on = None

def upgrade() -> None:
    op.create_table("organizations", sa.Column("organization_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False, unique=True), sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_table("memberships", sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.organization_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subject", sa.String(256), primary_key=True), sa.Column("role", sa.String(32), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.add_column("cases", sa.Column("organization_id", sa.String(36), nullable=True))
    op.add_column("cases", sa.Column("retention_until", sa.DateTime(), nullable=True))
    op.add_column("cases", sa.Column("legal_hold", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_cases_organization", "cases", ["organization_id"])
    op.create_foreign_key("fk_cases_organization", "cases", "organizations", ["organization_id"], ["organization_id"])
    op.create_table("case_access", sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subject", sa.String(256), primary_key=True), sa.Column("permission", sa.String(16), nullable=False),
        sa.Column("granted_by", sa.String(256), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_table("deletion_requests", sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.organization_id")), sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False), sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"), sa.Column("requested_by", sa.String(256), nullable=False),
        sa.Column("reviewed_by", sa.String(256)), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()), sa.Column("reviewed_at", sa.DateTime()))
    op.create_index("ix_deletion_requests_status", "deletion_requests", ["status"])

def downgrade() -> None:
    op.drop_table("deletion_requests"); op.drop_table("case_access")
    op.drop_constraint("fk_cases_organization", "cases", type_="foreignkey")
    op.drop_column("cases", "legal_hold"); op.drop_column("cases", "retention_until"); op.drop_column("cases", "organization_id")
    op.drop_table("memberships"); op.drop_table("organizations")
