"""Safety contract for the optional created_at query-plan migration."""
from pathlib import Path

SQL = (Path(__file__).resolve().parents[1] / "scripts/migrations/20261029_intel_events_created_at_index.sql").read_text()


def test_migration_is_concurrent_additive_and_idempotent():
    statement = SQL.split("CREATE INDEX CONCURRENTLY IF NOT EXISTS", 1)
    assert len(statement) == 2
    assert "ix_intel_events_created_at" in statement[1]
    assert "ON public.intel_events (created_at DESC)" in statement[1]
    statements = "\n".join(line for line in SQL.splitlines() if not line.lstrip().startswith("--"))
    assert statements.count(";") == 1


def test_migration_does_not_mutate_or_destroy_evidence():
    sql = "\n".join(line for line in SQL.splitlines() if not line.lstrip().startswith("--")).upper()
    assert not any(word in sql for word in ("DELETE ", "TRUNCATE ", "DROP ", "UPDATE ", "ALTER TABLE", "VACUUM ", "REINDEX "))
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in sql
