"""005 durable background jobs."""
from alembic import op
import sqlalchemy as sa
revision = "005"; down_revision = "004"; branch_labels = None; depends_on = None

def upgrade() -> None:
    op.create_table("jobs", sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(64), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("available_at", sa.DateTime(), server_default=sa.func.now()), sa.Column("lease_until", sa.DateTime()),
        sa.Column("worker_id", sa.String(128)), sa.Column("last_error", sa.Text()), sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_jobs_claim", "jobs", ["status", "available_at", "lease_until"])

def downgrade() -> None:
    op.drop_table("jobs")
