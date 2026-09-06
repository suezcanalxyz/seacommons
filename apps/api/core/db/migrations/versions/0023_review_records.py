"""add append-only review records

Revision ID: 0023_review_records
Revises: 0022_audio_artifacts
Create Date: 2026-09-06
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
revision="0023_review_records"
down_revision="0022_audio_artifacts"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    if "review_records" in set(sa.inspect(bind).get_table_names()): return
    op.create_table("review_records",
        sa.Column("review_id",sa.String(64),primary_key=True),
        sa.Column("target_type",sa.String(32),nullable=False),
        sa.Column("target_id",sa.String(256),nullable=False),
        sa.Column("target_version",sa.String(128),nullable=False),
        sa.Column("evidence_snapshot_id",sa.String(256),nullable=False),
        sa.Column("decision",sa.String(32),nullable=False),
        sa.Column("rationale",sa.Text(),nullable=False),
        sa.Column("actor",sa.String(256),nullable=False),
        sa.Column("reviewed_at",sa.DateTime(),nullable=False),
        sa.Column("requested_transition",sa.String(32)),
        sa.Column("created_at",sa.DateTime(),nullable=False),
    )
    for name,cols in [
      ("ix_review_records_target_type",["target_type"]),("ix_review_records_target_id",["target_id"]),
      ("ix_review_records_decision",["decision"]),("ix_review_records_actor",["actor"]),
      ("ix_review_records_reviewed_at",["reviewed_at"]),("ix_review_records_target_version",["target_type","target_id","target_version"])]:
        op.create_index(name,"review_records",cols)

def downgrade():
    bind=op.get_bind()
    if "review_records" not in set(sa.inspect(bind).get_table_names()): return
    for name in ["ix_review_records_target_version","ix_review_records_reviewed_at","ix_review_records_actor","ix_review_records_decision","ix_review_records_target_id","ix_review_records_target_type"]:
        op.drop_index(name,table_name="review_records")
    op.drop_table("review_records")
