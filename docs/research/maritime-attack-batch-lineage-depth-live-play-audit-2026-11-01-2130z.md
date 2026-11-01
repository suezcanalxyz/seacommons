# SeaCommons — attack batch-lineage depth guard and read-only LIVE/PLAY audit

Audit: 2026-11-01 21:29–21:31 UTC. Branch: `feature/maritime-attack-correlation-20261030`. Previous branch head: `dc704cea0414b28e0e36d3c1f80975269e9a5bed`. All changes are staging-only.

## Concrete correctness defect and fix

The bounded batch lineage traversal in `apps/api/core/intel/maritime_attack_batch_readonly.py` previously stopped after eight database-fetch rounds without checking whether the last round discovered unqueried ancestors. The cached single-episode verifier then saw no edges beyond that boundary and could incorrectly treat two publications as independent when their common origin was just outside the batch fetch. This is a **false-positive corroboration risk**, not merely a performance issue.

Fix: if `frontier` remains nonempty after the eighth round, return `batch_lineage_depth_limit` for the selected episodes. Do not claim the graph is complete or automatically promote an attack. No DB write, migration, collector, new VM job, or publication is introduced.

Three new regressions in `tests/test_maritime_attack_batch_readonly.py`:
1. Two outlets with separate eight-hop chains that merge at an unseen common ancestor must fail closed.
2. An ancestor reached exactly at the fetch boundary is not presumed terminal, even if a synthetic fixture has no additional edge.
3. A completely fetched short lineage with genuinely distinct roots still passes.

Commits: `2a328143521eaa42b8a24cdc2cb3041129e02f1f` (guard) and `cf033b0b5926de9cac8b9ff99dd5a0e1661ee7a2` (regressions).

CI: https://github.com/suezcanalxyz/seacommons/actions/runs/41352249105, four jobs SUCCESS. Unit log: 339 maritime attack tests PASS, 19 official bulletin tests PASS; isolated SQLite 3 PASS and PostgreSQL 6 PASS (367 Python tests total); frontend 5 JavaScript tests PASS and build SUCCESS. This certifies isolated staging tests, not real Oracle AIS or end-to-end production.

## Public HTTP GET audit (authorized remote, no writes)

At 2026-11-01 21:29 UTC, four endpoints returned HTTP 200:
- `https://play.seacommons.org/api/v1/play/counts`: total_count=3576, maritime_count=3447, humanitarian_count=129, investigation_count=3437; generated_at=2026-11-01T20:42:23.686085+00:00.
- `https://play.seacommons.org/api/v1/play/incidents?limit=1`: total_count=3576; generated_at=2026-11-01T21:29:27.291272+00:00. Counts match but are ~47 minutes apart; not an atomic snapshot.
- `https://live.seacommons.org/api/v1/live/pipeline`: generated_at=2026-11-01T21:29:27.546582+00:00. AIS, first-party and public feeds live; partner and radio degraded. Radio DSC accepted=47; NAVTEX accepted=0. A running decoder is not evidence of usable NAVTEX ingestion.
- `https://seacommons.org/api/v1/live/signals?mode=maritime`: 9 public maritime features, 8 security-domain and 1 safety-domain, at 2026-11-01T21:29:30.574554+00:00. No claim of attack-specific LIVE publication or end-to-end attack projection.

## Rolling incident candidates and October retrospective

Rolling 72h at 21:29 UTC: 2026-10-29 21:29 UTC to 2026-11-01 21:29 UTC. Candidate references only, not new database incidents:
- MSCIO 159/26, event 2026-10-29 22:12 UTC, ~25 NM NE of Khasab, two explosive devices reportedly attached to a tanker; IMO/MMSI unverified. Official source: https://mscio.eu/alerts/195 (webpage display published Oct 30, 07:44; display timezone not independently verified).
- MSCIO 162/26, event 2026-10-30 18:00 UTC, ~40 NM S of Lavan Island, unknown projectile reportedly struck a vessel with fire; vessel identity unverified. Official source: https://mscio.eu/alerts/198 (display published Oct 30, 22:17; timezone not independently verified).
- MSCIO 160/26, event 2026-10-30 02:25 UTC, Gulf of Aden, is a negative control: suspicious approach without shots or boarding attempt; **not** a confirmed physical attack. https://mscio.eu/alerts/196 .
- AL MAYEDA, IMO 9397298 and reported MMSI 538003356, operator-reported impact evening Oct 30: original event time, geolocation, independent witness and live AIS receipts still unverified; do not merge with MSCIO 162/26 by approximate time/region alone.
- CONTSHIP JET, IMO 9348625, MMSI 636019532, October retrospective, event 2026-10-28 10:00 UTC: Bulgarian MoD https://www.mod.bg/news9664 describes three observed strikes, but does not itself publish IMO/MMSI. Operator https://contships-management.com/2026/10/29/contships-management-inc-company-update/ relays Master's statement; not yet a certified independent original. Historical AIS speed change remains context, not attack proof.

Black Sea risk context: MARAD 2026-012 active until 2027-03-22, https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations . Advisory is not evidence for a particular incident.

**Reuse warning:** MSCIO's public Terms of Service at https://mscio.eu/terms-of-service/ restrict publication/redistribution of website information; publicly readable does not mean open-licensed. Do not mass copy, republish alert text or automatically redistribute source content without rights review. This run only inspected pages and retained references. No source-to-collector latency could be measured; webpage publication display timezone remains unresolved. GDELT, ONI, UKMTO, NATO Shipping Centre and NAVTEX coverage is not claimed as fully audited in this run.

## Oracle PostgreSQL

The authorized device is online; `pg_isready -h 127.0.0.1 -p 5432` reports accepting connections. A noninteractive `psql -w -X` read-only transaction attempt returned `FATAL: role "ubuntu" does not exist` before SQL execution. No escalation or credential changes. **Zero successful new Oracle SQL queries**. Tables `intel_events`, `vessel_tracks`, `alert_events`, `anomaly_events`, `humanitarian_incidents`, `forensic_events` and real `received_at` for CONTSHIP JET remain unverified.

Prepared, NOT executed:
```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '6000ms';
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('intel_events','vessel_tracks','alert_events',
                     'anomaly_events','humanitarian_incidents','forensic_events')
ORDER BY table_name, ordinal_position;
SELECT id, mmsi, ts, received_at, sog, lat, lon
FROM vessel_tracks
WHERE mmsi = '636019532'
  AND ts >= TIMESTAMP '2026-10-28 09:30:00'
  AND ts < TIMESTAMP '2026-10-28 11:30:00'
ORDER BY ts, id LIMIT 257;
ROLLBACK;
```

## Release gate

No production deploy, DB mutation, incident promotion, historical rewrite, data deletion, VM cron/timer/loop or duplicate automation. Next: acquire authorized Oracle read-only access, validate AIS receipt chronology, certify independent original attack witnesses, then run reviewed PLAY attack-only projection and human promotion tests with humanitarian isolation.
