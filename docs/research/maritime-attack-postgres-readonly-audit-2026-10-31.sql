-- SeaCommons staging: operator-run, READ-ONLY incident correlation audit.
-- Prepared 2026-10-31; NOT executed on Oracle (Desktop Commander quota exhausted).
-- Run in an explicitly read-only PostgreSQL connection with least-privilege credentials.
-- All statements are SELECT; statement_timeout prevents runaway scans.
-- Avoid dumping raw humanitarian content or unredacted forensic sensor payloads.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5000ms';
SET LOCAL lock_timeout = '1000ms';

-- Verify PostgreSQL time used for rolling 72h window.
SELECT now() AT TIME ZONE 'UTC' AS audit_utc;

-- 1. Maritime intel candidate IDs, source, original/publication/receipt times.
SELECT id, timestamp_utc, source_timestamp_utc, received_at, created_at,
       type, maritime_domain, operational_tier, source, linked_mmsi,
       title, url, lat, lon, location_uncertainty_m, coordinate_review_status
FROM intel_events
WHERE timestamp_utc >= to_char(now() AT TIME ZONE 'UTC' - interval '72 hours', 'YYYY-MM-DD"T"HH24:MI:SS')
  AND timestamp_utc < '2026-11-02'
  AND (maritime_domain IS DISTINCT FROM 'humanitarian')
ORDER BY timestamp_utc DESC LIMIT 100;

-- 2. October retro: candidate headlines and identifiers, no full-text dump.
SELECT id, timestamp_utc, type, source, linked_mmsi, title, url, lat, lon
FROM intel_events
WHERE timestamp_utc >= '2026-10-01' AND timestamp_utc < '2026-11-01'
  AND (maritime_domain IS DISTINCT FROM 'humanitarian')
  AND (title ILIKE '%attack%' OR title ILIKE '%struck%'
       OR title ILIKE '%sunk%' OR title ILIKE '%drone%'
       OR title ILIKE '%missile%' OR title ILIKE '%explosion%'
       OR title ILIKE '%CONTSHIP%')
ORDER BY timestamp_utc DESC LIMIT 100;

-- 3. CONTSHIP JET AIS: include reported time AND receipt time to detect stale/replayed positions.
-- AIS alone is never proof of an attack or of the vessel's operational status.
SELECT id, mmsi, ts, received_at, lat, lon, sog, cog, heading, nav_status, source
FROM vessel_tracks
WHERE mmsi = '636019532'
  AND ts >= timestamp '2026-10-27 00:00:00'
  AND ts < timestamp '2026-11-01 00:00:00'
ORDER BY ts DESC LIMIT 150;

-- 4. Other vessel positions, 72h sample for ingestion latency assessment.
SELECT mmsi, max(ts) AS latest_reported, max(received_at) AS latest_received,
       count(*) AS sample_count
FROM (
    SELECT mmsi, ts, received_at FROM vessel_tracks
    WHERE ts >= (now() AT TIME ZONE 'UTC' - interval '72 hours')
    ORDER BY ts DESC LIMIT 5000
) recent_tracks
GROUP BY mmsi ORDER BY latest_reported DESC LIMIT 100;

-- 5. Alert/anomaly/forensic: IDs and classifications only.
SELECT event_id, timestamp_utc, domain, status, lat, lon, created_at
FROM alert_events
WHERE timestamp_utc >= to_char(now() AT TIME ZONE 'UTC' - interval '72 hours', 'YYYY-MM-DD"T"HH24:MI:SS')
ORDER BY timestamp_utc DESC LIMIT 100;

SELECT event_id, timestamp_utc, anomaly_type, sensor_source, confidence, lat, lon
FROM anomaly_events
WHERE timestamp_utc >= '2026-10-01' AND timestamp_utc < '2026-11-01'
ORDER BY timestamp_utc DESC LIMIT 100;

SELECT event_id, timestamp_utc, classification, confidence, vessel_id, created_at
FROM forensic_events
WHERE timestamp_utc >= '2026-10-01' AND timestamp_utc < '2026-11-01'
ORDER BY timestamp_utc DESC LIMIT 100;

-- 6. Humanitarian separation: aggregate only, never reclassify as maritime attacks.
SELECT lifecycle, incident_status, count(*) AS cases,
       max(updated_at) AS most_recent_update
FROM humanitarian_incidents
GROUP BY lifecycle, incident_status ORDER BY cases DESC LIMIT 30;

-- 7. Canonical PLAY episodes: verify publication flags without writing.
SELECT episode_id, episode_family, status, verification_status,
       independence_groups, observation_ids, subject_ids,
       start_at, end_at, updated_at,
       behaviour_context->'analysis'->>'publication_state' AS publication_state
FROM maritime_episodes
WHERE start_at >= timestamp '2026-10-01 00:00:00'
  AND start_at < timestamp '2026-11-01 00:00:00'
ORDER BY start_at DESC LIMIT 100;

-- 8. Canonical observations: source time vs receipt; report URLs and lineage roots.
SELECT observation_id, service, lane, source_name, source_id,
       source_url, observed_at, received_at, provenance
FROM source_observations
WHERE received_at >= (now() AT TIME ZONE 'UTC' - interval '72 hours')
  AND service <> 'humanitarian'
ORDER BY received_at DESC LIMIT 100;

-- 9. Indexed lineage lookup only for the selected CONTSHIP observation IDs.
-- Replace the empty array with IDs returned by the preceding episode query.
-- Do NOT run an unbounded lineage_edges scan.
SELECT id, from_observation_id, to_observation_id, relation,
       method_version, confidence, detected_at
FROM lineage_edges
WHERE from_observation_id = ANY(ARRAY[]::text[])
ORDER BY detected_at DESC LIMIT 100;

ROLLBACK;
