# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md Phase 2.2 -- Alembic is the schema authority.

`alembic upgrade head` on a fresh database must produce exactly the schema
the live models describe, and downgrade must be reversible.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect

from core.db.models import Base

alembic_command = pytest.importorskip("alembic.command")
from core.db.session import alembic_config  # noqa: E402


def _config(db_url: str):
    cfg = alembic_config()
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _schema(engine) -> dict[str, set[str]]:
    inspector = inspect(engine)
    return {
        table: {col["name"] for col in inspector.get_columns(table)}
        for table in inspector.get_table_names()
        if table != "alembic_version"
    }


def test_upgrade_head_matches_the_model_metadata(tmp_path):
    migrated_url = f"sqlite:///{tmp_path / 'migrated.db'}"
    alembic_command.upgrade(_config(migrated_url), "head")
    migrated = _schema(create_engine(migrated_url))

    reference_engine = create_engine(f"sqlite:///{tmp_path / 'reference.db'}")
    Base.metadata.create_all(reference_engine)
    reference = _schema(reference_engine)

    assert migrated == reference
    assert "intel_events" in migrated
    # Phase 2.2 canonical classification columns landed via 0002.
    assert {
        "schema_version", "maritime_domain", "operational_tier",
        "humanitarian_case_type", "incident_lifecycle", "location_status",
        "coordinate_review_status", "location_uncertainty_m",
    } <= migrated["intel_events"]

    migrated_indexes = {
        idx["name"]
        for idx in inspect(create_engine(migrated_url)).get_indexes("intel_events")
    }
    assert "ix_intel_events_humanitarian_case_type" in migrated_indexes
    assert "ix_intel_events_incident_lifecycle" in migrated_indexes


def test_downgrade_then_upgrade_is_clean(tmp_path):
    # 0004 (lossless event ids) is deliberately widening-only -- its downgrade
    # raises rather than truncate identifiers. The reversible span is base..0003.
    url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    cfg = _config(url)
    alembic_command.upgrade(cfg, "0003_intel_composite_idx")
    alembic_command.downgrade(cfg, "base")
    assert _schema(create_engine(url)) == {}
    alembic_command.upgrade(cfg, "head")
    assert "intel_events" in _schema(create_engine(url))


def test_lossless_event_id_downgrade_is_blocked(tmp_path):
    import pytest

    url = f"sqlite:///{tmp_path / 'block.db'}"
    cfg = _config(url)
    alembic_command.upgrade(cfg, "head")
    with pytest.raises(Exception, match="widening-only"):
        alembic_command.downgrade(cfg, "0003_intel_composite_idx")
