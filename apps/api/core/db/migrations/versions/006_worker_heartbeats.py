"""006 worker heartbeats."""
from alembic import op
import sqlalchemy as sa
revision = "006"; down_revision = "005"; branch_labels = None; depends_on = None

def upgrade() -> None:
    op.create_table("worker_heartbeats", sa.Column("worker_id", sa.String(128), primary_key=True),
        sa.Column("hostname", sa.String(256), nullable=False), sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("current_job_id", sa.String(36)), sa.Column("started_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_worker_heartbeats_seen", "worker_heartbeats", ["last_seen_at"])

def downgrade() -> None:
    op.drop_table("worker_heartbeats")
