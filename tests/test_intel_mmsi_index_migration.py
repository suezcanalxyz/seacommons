"""Predeploy contract: index plan is non-destructive and explicit opt-in."""
from pathlib import Path
from sqlalchemy import Index
from core.db.models import IntelEventDB

MIGRATION = Path(__file__).resolve().parents[1] / 'scripts/migrations/20261029_intel_events_mmsi_index.sql'


def test_mmsi_lookup_is_a_real_indexable_column():
    assert 'linked_mmsi' in IntelEventDB.__table__.columns
    assert IntelEventDB.__table__.columns['linked_mmsi'].type.length == 16


def test_migration_is_idempotent_concurrent_and_non_destructive():
    statements = '\n'.join(line for line in MIGRATION.read_text().splitlines() if not line.lstrip().startswith('--')).strip().lower()
    assert statements.count('create index concurrently if not exists') == 1
    assert 'on public.intel_events (linked_mmsi)' in statements
    assert statements.endswith(';')
    assert all(unsafe not in statements for unsafe in ('drop ', 'delete ', 'truncate ', 'update ', 'alter table'))
