-- SeaCommons predeployment performance migration. NOT auto-applied.
-- Require full off-host PostgreSQL backup, isolated restore and rollback approval.
-- Execute outside a transaction: CREATE INDEX CONCURRENTLY cannot run in one.
-- Read-only EXPLAIN 2026-10-29: latest 200 events and recent two-hour
-- events both use Parallel Seq Scan + Sort on intel_events (~409k rows).
-- Used by humanitarian truth-table and AIS/humanitarian correlation windows.
-- Idempotent, additive; never removes evidence or existing indexes.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_intel_events_created_at
    ON public.intel_events (created_at DESC);
