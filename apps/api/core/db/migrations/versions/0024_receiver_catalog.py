"""persistent receiver catalog

Revision ID: 0024_receiver_catalog
Revises: 0023_review_records
Create Date: 2026-09-07
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
revision = "0024_receiver_catalog"
down_revision = "0023_review_records"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if "receiver_catalog" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "receiver_catalog",
        sa.Column("discovery_key", sa.String(256), primary_key=True),
        sa.Column("receiver_id", sa.String(128)),
        sa.Column("public_label", sa.String(128), nullable=False),
        sa.Column("network_family", sa.String(32), nullable=False),
        sa.Column("physical_lineage", sa.String(128)),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("directory_source", sa.String(64), nullable=False),
        sa.Column("license_class", sa.String(32), nullable=False, server_default="public_access"),
        sa.Column("source_terms", sa.Text()),
        sa.Column("terms_status", sa.String(32), nullable=False),
        sa.Column("activation_status", sa.String(32), nullable=False),
        sa.Column("country", sa.String(8)), sa.Column("lat", sa.Float()), sa.Column("lon", sa.Float()),
        sa.Column("capabilities", sa.JSON()), sa.Column("reachable", sa.Boolean()),
        sa.Column("uptime_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("failure_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("available_slots", sa.Integer()), sa.Column("last_discovered_at", sa.DateTime(), nullable=False),
        sa.Column("last_probed_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for name, cols in (("ix_receiver_catalog_receiver_id", ["receiver_id"]), ("ix_receiver_catalog_lineage", ["physical_lineage"]), ("ix_receiver_catalog_family", ["network_family"]), ("ix_receiver_catalog_source", ["directory_source"]), ("ix_receiver_catalog_terms", ["terms_status"]), ("ix_receiver_catalog_activation", ["activation_status"]), ("ix_receiver_catalog_score", ["score"])):
        op.create_index(name, "receiver_catalog", cols)

def downgrade():
    if "receiver_catalog" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("receiver_catalog")
