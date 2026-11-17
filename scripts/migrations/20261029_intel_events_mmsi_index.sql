-- SeaCommons predeployment performance migration. NOT auto-applied.
-- Apply only after full off-host backup, isolated restore drill, and rollback approval.
-- CREATE INDEX CONCURRENTLY must run outside a transaction block.
-- Evidence: EXPLAIN on 2026-10-29 showed Seq Scan on intel_events for
-- linked_mmsi equality (409k rows); follow-up fusion and cross-source
-- hypothesis queries filter this field.
-- Idempotent; preserves all existing rows and indexes.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_intel_events_linked_mmsi
    ON public.intel_events (linked_mmsi);
