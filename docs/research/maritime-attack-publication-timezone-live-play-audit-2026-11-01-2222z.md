# Maritime attack correlation — publication timezone and LIVE/PLAY audit
**Audit window:** 2026-11-01 22:19–22:22 UTC. **Scope:** staging branch only; production read-only HTTP. **Baseline:** f8b998c5.

## Code change (staging only)
- `apps/api/core/intel/maritime_attack_independence_readonly.py`: distinguish legacy naive UTC PostgreSQL observation/receipt clocks from externally supplied publication clocks. Publication times without explicit timezone are now rejected with `invalid_publication_timestamp` rather than silently interpreted as UTC.
- `tests/test_maritime_attack_independence_readonly.py`: three regressions: naive ISO publication rejected, naive Python datetime publication rejected, naive UTC DB receipt with explicitly offset publication accepted.
- This is a *corroboration guard*, not a new ingestion job, timer, incident promotion, or publication mechanism.
- Functional commits: `f78b97762883db68fcf69644418799ca254bd529` and `bb2ccccbf61b5221842b62df03007ca24d2eb892`.
- CI run `41356644310` on the latter commit: success. 342 correlation Python tests, 19 official bulletin tests, 3 isolated SQLite tests, 6 isolated PostgreSQL tests, 5 frontend JavaScript tests and successful frontend build; **370 Python tests total**. CI PostgreSQL is isolated and does not validate Oracle.

## Live public API read-only observations
- `GET https://api.seacommons.org/api/v1/play/counts` HTTP 200: `total_count=3576`, `maritime_count=3447`, `humanitarian_count=129`, `investigation_count=3437`; payload `generated_at=2026-11-01T22:20:58.240428+00:00`.
- `GET /api/v1/play/cache-status` HTTP 200: catalog ready and counts ready; catalog generated at `2026-11-01T22:21:22.959509+00:00`, counts generated at `2026-11-01T22:20:58.240428+00:00`. Separate cache timestamps mean numerical equality is not transactional synchronization.
- `GET /api/v1/play/incidents?limit=50` HTTP 200: `total_count=3576`; 50 rows returned, no `incident_type` containing `attack` in this page. This is NOT a full-catalog assertion.
- `GET /api/v1/live/signals?limit=100` HTTP 200: two features returned, both with `incident_type=distress`; zero attack labels in this response. This is NOT an assertion about every LIVE layer.
- `GET /api/v1/live/pipeline` HTTP 200: AIS, first-party and public feeds `live`; partner and radio `degraded`. Radio decoder: `dsc_accepted=47`, `navtex_accepted=0`. Running radio service does not prove usable NAVTEX observations.
- HTTP checks were performed with short timeouts and did not mutate data.

## Oracle PostgreSQL access
A read-only `psql -X -w` attempt with default local role was rejected before SQL: `FATAL: role "ubuntu" does not exist`. **Zero Oracle SQL statements completed.** No privilege change, credential extraction, DB writes, migrations or data deletions.

The following queries are **prepared, not executed**, for an authorized read-only connection. Verify column names against `information_schema.columns` before using vessel filters:

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '5s';
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('intel_events', 'vessel_tracks', 'alert_events',
                     'anomaly_events', 'humanitarian_incidents', 'forensic_events')
ORDER BY table_name, ordinal_position;
SELECT mmsi, ts, received_at, lat, lon, sog
FROM vessel_tracks
WHERE mmsi IN ('636019532', '538003356')
  AND ts >= '2026-10-28 00:00:00'
  AND ts <  '2026-11-02 00:00:00'
ORDER BY mmsi, ts
LIMIT 300;
ROLLBACK;
```

## Source verification and candidate cases
- **CONTSHIP JET**, IMO 9348625, MMSI 636019532 (identity crosswalk from earlier audits), attack 28 October at 10:00 UTC: Bulgarian Ministry of Defence reports three impacts and rescue; official bulletin contains name but no IMO/MMSI. The ministry's footer permits copying public information with explicit attribution. https://www.mod.bg/news9664
- Contships Management identifies CONTSHIP JET and IMO 9348625 and relays the Master's statement; website article dated 29 October, document headed Athens 28 October. Publication clock is *date only*, so it cannot be invented as minute-precise for independent corroboration. https://contships-management.com/2026/10/29/contships-management-inc-company-update/
- **MSCIO 159/26**, event 29 October 22:12 UTC, Strait of Hormuz: tanker, explosive devices attached to hull, identity not confirmed. https://mscio.eu/alerts/195
- **MSCIO 162/26**, event 30 October 18:00 UTC, Arabian Gulf: vessel struck, onboard fire, identity not confirmed. Do not equate with AL MAYEDA without cross-document evidence. https://mscio.eu/alerts/198
- **AL MAYEDA**, event evening 30 October: Nakilat confirms unidentified objects struck vessel; no weapon or attacker attributed. https://nakilat.com/al-mayeda-vessel-incident-in-the-arabian-gulf/
- **MSCIO 160/26** is a negative control: 30 October Gulf of Aden suspicious approach, explicitly no shots or boarding attempt. https://mscio.eu/alerts/196
- **MSCIO 163/26** is a retrospective late report for 28 October; publication 30 October. Do not mistake publication for event time. https://mscio.eu/alerts/199
- **MARAD 2026-012** remains an active Black Sea/Sea of Azov *regional risk advisory*, not a case-specific witness. https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations
- **MSCIO license caution:** publicly readable pages are not freely redistributable; site terms restrict republication. Store citation URL and metadata for internal review; no bulk copying or public redistribution without authorization. https://www.mscio.eu/terms-of-service/

## Open gates / next action
1. Obtain approved Oracle read-only role and verify `received_at` for CONTSHIP JET and AL MAYEDA; audit the six named tables and current LIVE/PLAY linkage. No invented counts.
2. Measure collector source publication → receipt → canonical observation → PLAY availability latency from actual DB timestamps; public HTTP snapshots alone cannot establish this.
3. Complete operator-reviewed original-source lineage and IMO/MMSI crosswalk; AIS gaps/stops remain context, never proof.
4. End-to-end staging verification of PLAY candidate → reviewed incident and attack-specific coral UI; never auto-promote humanitarian drift or unknown aggressors.
5. No production deploy without explicit approval. No VM cron, loop, scheduler, database mutation, historical rewrite or deletion.
