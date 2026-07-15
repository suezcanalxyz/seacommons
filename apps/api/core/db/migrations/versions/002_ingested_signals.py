"""002 durable and idempotent inbound signals."""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingested_signals",
        sa.Column("signal_id", sa.String(36), primary_key=True),
        sa.Column("source_channel", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(256), nullable=False),
        sa.Column("provider_message_id", sa.String(256), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("source_channel", "provider_message_id", name="uq_ingested_signal_delivery"),
    )
    op.create_index("ix_ingested_signals_channel", "ingested_signals", ["source_channel"])
    op.create_index("ix_ingested_signals_received", "ingested_signals", ["received_at"])


def downgrade() -> None:
    op.drop_table("ingested_signals")
