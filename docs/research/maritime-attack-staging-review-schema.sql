-- SeaCommons maritime-attack review: dedicated PostgreSQL STAGING DATABASE ONLY.
-- NEVER execute against Oracle production, even under a separate schema.
-- Apply manually only after verifying SELECT current_database() ends in _staging.
-- No production deployment, automatic migration, background job or publication.
BEGIN;
DO $$
BEGIN
    IF current_database() !~ '^[a-z][a-z0-9_]*_staging$' THEN
        RAISE EXCEPTION 'Dedicated staging database required, got %', current_database();
    END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS attack_review_staging;
REVOKE ALL ON SCHEMA attack_review_staging FROM PUBLIC;
CREATE TABLE IF NOT EXISTS attack_review_staging.review_snapshots (
    snapshot_id char(64) PRIMARY KEY,
    case_review_id text NOT NULL,
    attack_observation_id text NOT NULL,
    evidence_ledger_sha256 char(64) NOT NULL,
    snapshot_sha256 char(64) NOT NULL,
    payload_json text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT review_snapshot_id_hex CHECK (snapshot_id ~ '^[0-9a-f]{64}$'),
    CONSTRAINT review_payload_sha_hex CHECK (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT review_evidence_sha_hex CHECK (evidence_ledger_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT review_payload_json_valid CHECK (jsonb_typeof(payload_json::jsonb) = 'object')
);
REVOKE ALL ON attack_review_staging.review_snapshots FROM PUBLIC;
CREATE INDEX IF NOT EXISTS review_snapshots_case_idx
    ON attack_review_staging.review_snapshots (case_review_id, recorded_at DESC);
-- Provision a separate non-superuser role with only USAGE on this schema and
-- SELECT/INSERT on this table. Do not grant UPDATE, DELETE, TRUNCATE or DDL.
-- No automatic privileges are granted here.
COMMIT;
