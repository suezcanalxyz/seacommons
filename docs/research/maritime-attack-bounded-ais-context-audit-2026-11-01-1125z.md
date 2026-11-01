# Maritime attack correlation — bounded AIS read path and staging audit

Date: 2026-11-01, 11:25 UTC. Branch: `feature/maritime-attack-correlation-20261030`.
Baseline: `1a3e0a2e`. This report is an append-only development note,
not a claim that any incident was published.

## Changes and verified tests

- `maritime_attack_ais_context_readonly.py`: opt-in, bounded context query
  for `VesselTrackDB`. Requires caller-owned PostgreSQL transaction with
  `transaction_read_only=on`; uses `no_autoflush`, indexed MMSI/time
  filter, a maximum of 512 rows, and no writes or commits.
- Invalid or duplicate track IDs, missing receipt clocks, malformed
  geometry, unexpected MMSI, out-of-window rows and truncated results
  fail closed, returning no partial AIS context.
- The result retains original `vessel_tracks.id` values and preserves
  `ts` separately from `received_at`. It is never a documentary witness.
- New pure tests include the CONTSHIP JET 09:59:22 → 10:34:46 speed
  reduction, negative cases and row-cap/UTC guards.
- Ephemeral PostgreSQL 16 CI tests reject a read-write transaction and
  accept an explicit READ ONLY transaction; no Oracle credentials.
- Existing GitHub Actions workflow only; no new VM cron/timer/scheduler.

CI run 41301718474 for commit `8d349bf4`:
293 maritime unit tests + 18 official adapter tests + 3 SQLite tests
+ 6 PostgreSQL tests = **320 Python PASS**.
Frontend 5/5 PASS, Vite build successful, all four jobs SUCCESS.
https://github.com/suezcanalxyz/seacommons/actions/runs/41301718474

This does not certify an end-to-end operational PLAY promotion. The new
database adapter has been tested on an empty ephemeral PostgreSQL table;
actual CONTSHIP JET receipt timestamps from Oracle remain unverified.

## LIVE/PLAY read-only public GET

At ~11:25 UTC:
- `https://play.seacommons.org/api/v1/play/counts`: HTTP 200,
  generated 11:22:41 UTC, 3,569 total = 3,442 maritime + 127 humanitarian.
- `https://play.seacommons.org/api/v1/play/incidents?limit=1`: HTTP 200,
  generated 11:25:05 UTC, 3,570 total.
- `https://live.seacommons.org/api/v1/live/pipeline`: HTTP 200,
  generated 11:25:06 UTC; AIS, first-party and public feeds live;
  partner inputs degraded.

The one-element PLAY discrepancy reflects distinct generation times;
do not call it a persistent error without a synchronized snapshot.
HTTP 200 is not proof of source ingestion or attack corroboration.

## Oracle PostgreSQL audit

The authorized remote device is online and PostgreSQL is running.
A default `psql` connection fails because role `ubuntu` does not exist.
A follow-up attempt to execute an explicit read-only audit through the
application connection was blocked by tool safety controls. No
new SQL results are certified in this run. Prior counts remain historical.

Reproducible read-only SQL for a future authorized audit:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '7000ms';
SELECT now() AT TIME ZONE 'UTC' AS snapshot_utc;
SELECT count(*) FROM intel_events WHERE created_at >= now()-interval '72 hours';
SELECT count(*) FROM alert_events WHERE created_at >= now()-interval '72 hours';
SELECT count(*) FROM anomaly_events WHERE created_at >= now()-interval '72 hours';
SELECT count(*) FROM humanitarian_incidents WHERE updated_at >= now()-interval '72 hours';
SELECT count(*) FROM forensic_events WHERE created_at >= now()-interval '72 hours';
SELECT count(*) FROM maritime_episodes WHERE created_at >= now()-interval '72 hours';
SELECT count(*) FROM source_observations
 WHERE received_at >= '2026-10-01'
   AND (observation_type = 'official_maritime_bulletin'
    OR source_name ~* '(MSCIO|UKMTO|NAVAREA|NAVWARN|Bulgarian Ministry|MARAD|GDELT)');
SELECT id, mmsi, ts, received_at, sog, lat, lon FROM vessel_tracks
 WHERE mmsi = '636019532'
   AND ts BETWEEN '2026-10-28 09:30:00' AND '2026-10-28 11:30:00'
 ORDER BY ts, id LIMIT 257;
ROLLBACK;
```

The query is a template, not an executed result. Do not promote based on
a missing AIS row, a sudden stop, a replay, or a source URL count.

## Documentary candidates and provenance

- CONTSHIP JET, IMO 9348625, MMSI 636019532, 28 Oct 10:00 UTC:
  Bulgarian Ministry of Defence primary report (three observed impacts);
  https://www.mod.bg/news9664 .
  Prior AIS evidence: 10.2 kn at 09:59:22 and 0.6 kn at 10:34:46 UTC.
  Source publication clock and actual AIS receipt clocks are not yet
  certified; AIS remains context, not independent attack proof.
- MSCIO 158/26, 29 Oct 16:00 UTC, Strait of Hormuz:
  https://mscio.eu/alerts/194 ; unknown vessel IMO/MMSI.
- MSCIO 159/26, 29 Oct 22:12 UTC, Strait of Hormuz:
  https://mscio.eu/alerts/195 ; two devices on tanker hull;
  UKMTO publication may share upstream origin.
- MSCIO 162/26, 30 Oct 18:00 UTC, Arabian Gulf:
  https://mscio.eu/alerts/198 ; unknown vessel IMO/MMSI.
- MSCIO 163/26, published 30 Oct, describes 28 Oct attack:
  https://mscio.eu/alerts/199 ; not a fresh 30 Oct attack.
- MSCIO 161/26, AZINI reported hijacked 29 Oct 09:00 UTC:
  https://mscio.eu/alerts/197 ; 30 Oct coordinates are last-known
  position, not proven hijack site.
- IMO highlighted incident list (as of 30 Oct): 122 confirmed
  regional incidents, including GHANA PROSPERITY IMO 9732541 on
  3 and 23 October. These are separate episodes, not two sightings
  of one attack:
  https://www.imo.org/en/mediacentre/hottopics/pages/middle-east-highlighted-incidents.aspx
- MARAD 2026-012 Black Sea / Sea of Azov advisory:
  https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations
  is background risk, not a vessel-specific incident.

Reuse restrictions: MSCIO terms require careful review before reuse or
redistribution; IMO website material is not automatically available for
commercial reuse; Bulgarian MOD allows public information copying with
attribution. GDELT advertises a 15-minute update cadence, not a measured
SeaCommons ingestion delay. No restricted bulk content was ingested.

## Remaining release gates

1. Obtain an explicitly authorized read-only Oracle transaction and
   inspect CONTSHIP JET `ts` versus `received_at` with original row IDs.
2. In isolated staging, ingest licensed, reviewed official bulletin
   metadata through the existing canonical writer and preserve
   event/publication/receipt timestamps and lineage.
3. Validate true source-origin independence, dedup IMO/MMSI and separate
   attack vs sinking episodes; test false positives and false negatives.
4. Verify new incident category/color and operator-reviewed PLAY-to-incident
   transition end-to-end, separate from humanitarian drift.
5. Require explicit approval before any production deployment.

No production deploy, historical mutation, deletion or VM scheduling.
