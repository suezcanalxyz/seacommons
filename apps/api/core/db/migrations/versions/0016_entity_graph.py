# SPDX-License-Identifier: AGPL-3.0-or-later
"""entities, entity_relationships

Revision ID: 0016_entity_graph
Revises: 0015_lineage_edges
Create Date: 2026-09-04

docs/updates.md P2.3: entity graph -- "start with typed relational
objects/edges in PostgreSQL; evaluate specialized graph infrastructure
only if measured queries justify it." Two new tables, no data
migration. Same checkfirst guard as every prior migration in this
series: 0001_baseline's upgrade() runs create_all(checkfirst=True)
against live model metadata, so a fresh database already has both
tables (core.db.models.EntityDB / EntityRelationshipDB) by the time
0001 runs.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_entity_graph"
down_revision = "0015_lineage_edges"
branch_labels = None
depends_on = None

_ENTITIES = "entities"
_RELATIONSHIPS = "entity_relationships"


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    if _ENTITIES not in existing_tables:
        op.create_table(
            _ENTITIES,
            sa.Column("entity_id", sa.String(length=64), primary_key=True),
            sa.Column("entity_type", sa.String(length=32), nullable=False),
            sa.Column("canonical_key", sa.String(length=256), nullable=False),
            sa.Column("display_name", sa.String(length=256)),
            sa.Column("attributes", sa.JSON()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("entity_type", "canonical_key", name="uq_entity_type_canonical_key"),
        )
        op.create_index("ix_entities_entity_type", _ENTITIES, ["entity_type"])

    if _RELATIONSHIPS not in existing_tables:
        op.create_table(
            _RELATIONSHIPS,
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("from_entity_id", sa.String(length=64), nullable=False),
            sa.Column("to_entity_id", sa.String(length=64), nullable=False),
            sa.Column("relation_type", sa.String(length=32), nullable=False),
            sa.Column("provenance", sa.JSON()),
            sa.Column("valid_from", sa.String(length=32)),
            sa.Column("valid_to", sa.String(length=32)),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
            sa.Column("method_version", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_entity_relationships_from_entity_id", _RELATIONSHIPS, ["from_entity_id"])
        op.create_index("ix_entity_relationships_to_entity_id", _RELATIONSHIPS, ["to_entity_id"])
        op.create_index("ix_entity_relationships_relation_type", _RELATIONSHIPS, ["relation_type"])


def downgrade() -> None:
    op.drop_index("ix_entity_relationships_relation_type", table_name=_RELATIONSHIPS)
    op.drop_index("ix_entity_relationships_to_entity_id", table_name=_RELATIONSHIPS)
    op.drop_index("ix_entity_relationships_from_entity_id", table_name=_RELATIONSHIPS)
    op.drop_table(_RELATIONSHIPS)
    op.drop_index("ix_entities_entity_type", table_name=_ENTITIES)
    op.drop_table(_ENTITIES)
