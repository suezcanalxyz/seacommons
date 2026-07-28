"""008 partner-owned connectors and tenant-scoped signals."""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connectors",
        sa.Column("connector_id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.organization_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("external_account_id", sa.String(128)),
        sa.Column("external_channel_id", sa.String(128), nullable=False),
        sa.Column("display_address", sa.String(128)),
        sa.Column("secret_ref", sa.String(256)),
        sa.Column("publication_policy", sa.String(16), nullable=False, server_default="private"),
        sa.Column("configuration", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime()),
        sa.UniqueConstraint(
            "provider", "external_channel_id", name="uq_connector_provider_channel"
        ),
    )
    op.create_index("ix_connectors_organization_id", "connectors", ["organization_id"])
    op.create_index("ix_connectors_provider", "connectors", ["provider"])
    op.create_index("ix_connectors_status", "connectors", ["status"])
    op.add_column(
        "ingested_signals",
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.organization_id"),
            nullable=True,
        ),
    )
    op.add_column(
        "ingested_signals",
        sa.Column(
            "connector_id",
            sa.String(36),
            sa.ForeignKey("connectors.connector_id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_ingested_signals_organization_id",
        "ingested_signals",
        ["organization_id"],
    )
    op.create_index(
        "ix_ingested_signals_connector_id",
        "ingested_signals",
        ["connector_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingested_signals_connector_id", table_name="ingested_signals")
    op.drop_index("ix_ingested_signals_organization_id", table_name="ingested_signals")
    op.drop_column("ingested_signals", "connector_id")
    op.drop_column("ingested_signals", "organization_id")
    op.drop_table("connectors")
