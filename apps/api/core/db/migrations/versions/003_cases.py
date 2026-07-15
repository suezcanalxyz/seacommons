"""003 operational case management."""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("cases",
        sa.Column("case_id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("sensitivity", sa.String(16), nullable=False, server_default="restricted"),
        sa.Column("summary", sa.Text(), server_default=""),
        sa.Column("lat", sa.Float()), sa.Column("lon", sa.Float()), sa.Column("persons", sa.Float()),
        sa.Column("assigned_to", sa.String(256)), sa.Column("created_by", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_cases_status", "cases", ["status"])
    op.create_index("ix_cases_priority", "cases", ["priority"])
    op.create_table("case_signals",
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("signal_id", sa.String(36), sa.ForeignKey("ingested_signals.signal_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("linked_by", sa.String(256), nullable=False),
        sa.Column("linked_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_table("case_timeline",
        sa.Column("entry_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False), sa.Column("actor", sa.String(256), nullable=False),
        sa.Column("body", sa.Text(), server_default=""), sa.Column("data", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_case_timeline_case", "case_timeline", ["case_id"])


def downgrade() -> None:
    op.drop_table("case_timeline")
    op.drop_table("case_signals")
    op.drop_table("cases")
