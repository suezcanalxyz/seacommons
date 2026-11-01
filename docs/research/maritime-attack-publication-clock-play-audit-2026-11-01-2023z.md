# SeaCommons — canonical publication-clock gate and LIVE/PLAY read-only audit

Audit window: 2026-11-01 20:21–20:23 UTC. Branch: `feature/maritime-attack-correlation-20261030`. Previous head: `b7d47b5de082d8dfac4e3e1124adf780edd839fc`.

## Correctness change: prevent missing publication clocks from becoming two-source proof

The canonical `audit_attack_episode_independence(..., require_chronology=True)` used by the PLAY single/batch audit previously accepted an observation with `observed_at` and `received_at` but **no `published_at` or `published_at_utc`**. This could display an attack as independently corroborated without being able to audit when either original source was actually published. The stricter rule now returns `missing_publication_timestamp`; a day-only publication value returns `invalid_publication_timestamp`. Both publication aliases remain checked for contradictions, and publication after receipt still fails closed. The source observation is not modified, and a missing clock is never inferred from midnight or receipt time.

Changes:
- `apps/api/core/intel/maritime_attack_independence_readonly.py`: strict publication-clock gate.
- `tests/test_maritime_attack_independence_readonly.py`: missing-clock and date-only false-positive regressions; valid precise originals still pass.
- `tests/test_maritime_attack_batch_readonly.py`: strict batch missing-clock negative and two-original positive regression.
- Commits: `8c077411`, `9780c66b`, `5b7028bd`, `57d451b0`. The first three intermediate CI runs failed while the tests were being brought into alignment; final head CI is green.

Certified GitHub Actions run: https://github.com/suezcanalxyz/seacommons/actions/runs/41346526453 (commit `57d451b016ceb2d05c501e1b25966e053a49cf13`). Four jobs SUCCESS. Python: 336 attack/unit + 19 official bulletin + 3 SQLite + 6 isolated PostgreSQL = **364 PASS**; frontend 5 JavaScript PASS and Vite build SUCCESS. No Oracle test or production deployment.

## LIVE/PLAY public HTTP GET audit

At approximately 20:21–20:23 UTC, all endpoints returned HTTP 200:
- `https://play.seacommons.org/api/v1/play/counts`: total 3576, maritime 3447, humanitarian 129, investigation 3437; generated `2026-11-01T19:26:43.348940+00:00`.
- `https://play.seacommons.org/api/v1/play/incidents?limit=1`: total 3576; generated `2026-11-01T20:21:43.716538+00:00`. Counts agree, but snapshots are about 55 minutes apart: no claim of transaction-level consistency.
- `https://live.seacommons.org/api/v1/live/pipeline`: generated `2026-11-01T20:21:43.977609+00:00`. AIS, first-party, public-feed, radio reported live; partner degraded. Radio `dsc_accepted=47`, `navtex_accepted=0`: **NAVTEX ingestion unproven**, despite radio service state.
- `https://seacommons.org/api/v1/live/signals?mode=maritime`: at 20:23 UTC, ten features: visual categories 9 AIS gap and 1 navigation casualty; zero attack features. This is an observed public snapshot, NOT an end-to-end certification of the attack pipeline.

HTTP response timing and the source publication-to-collector delay are separate metrics; only the former was directly observed here.

## Rolling 72-hour candidates and October retrospective

Window at 20:21 UTC: 2026-10-29 20:21 UTC through 2026-11-01 20:21 UTC. All are **investigative candidates**, not newly promoted SeaCommons incidents.

- **MSCIO 159/26**: incident 2026-10-29 22:12 UTC, ~25 NM northeast of Khasab, Hormuz; small craft reportedly attached two devices to a tanker. Published 2026-10-30 07:44 (site display clock; timezone not explicitly verified here), roughly 9h32m after event if UTC. https://mscio.eu/alerts/195 . Vessel IMO/MMSI unknown; do not count another publisher of this alert as independent.
- **MSCIO 162/26**: incident 2026-10-30 18:00 UTC, ~40 NM south of Lavan Island; reported port-side impact and fire. Published 2026-10-30 22:17 (site display clock; timezone not explicitly verified here), roughly 4h17m after event if UTC. https://mscio.eu/alerts/198 . Vessel unknown; do not merge with AL MAYEDA on date and broad geography alone.
- **AL MAYEDA**: reported impact evening 2026-10-30, IMO 9397298 and reported MMSI 538003356; exact event time, position, independent witness, reuse rights and direct collector receipt remain unverified. Operator source previously identified: https://nakilat.com/al-mayeda-vessel-incident-in-the-arabian-gulf/ .
- **CONTSHIP JET** (October retrospective, outside rolling 72h): IMO 9348625, MMSI 636019532, attack 2026-10-28 10:00 UTC. Bulgarian MoD https://www.mod.bg/news9664 documents observed strikes but not the IMO/MMSI. Operator https://contships-management.com/2026/10/29/contships-management-inc-company-update/ supplies IMO and reports the Master's statement indirectly. AIS speeds 10.2 knots at 09:59:22 and 0.6 knots at 10:34:46 are **context, never independent attack evidence**. Sinking, if documented, is a subsequent outcome, not a duplicate attack.
- **MSCIO 160/26 negative control**: 2026-10-30 02:25 UTC, Gulf of Aden, position 11°57.4'N 045°04.5'E; suspicious approach, **no shots fired and no boarding attempt**. https://mscio.eu/alerts/196 . Do not classify as a documented physical attack.
- **AZINI / MSCIO 161/26**: alleged piracy/hijack event 2026-10-29 09:00 UTC, northeastern Somali coast; position at 04:00 UTC on Oct 30 and later update are **post-event positions**, not a verified hijack site. https://mscio.eu/alerts/197 .
- **MSCIO 163/26**: late-published 2026-10-30 alert describing an incident on **2026-10-28**. Event date and publication date must not be conflated. https://mscio.eu/alerts/199 .
- Black Sea advisory MARAD 2026-012: https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations ; risk context only, active to 2027-03-22, not proof of an individual attack.

These sources were checked as accessible public pages. Free viewing does not establish bulk-redistribution rights. No mass scraping or republishing. Source-to-SeaCommons ingestion latency was **not** measured.

## Oracle PostgreSQL audit status and prepared SQL

The authorized remote device is online. A noninteractive `psql -w -X` attempt with `BEGIN READ ONLY; SELECT current_user; ROLLBACK;` failed **before executing SQL**: `FATAL: role "ubuntu" does not exist`. No privilege, credential or configuration changes were attempted. **New Oracle queries completed: zero**; the six requested tables and real `vessel_tracks.received_at` remain unverified.

Prepared, NOT executed:
```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '6000ms';
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema='public' AND table_name IN
('intel_events','vessel_tracks','alert_events','anomaly_events',
 'humanitarian_incidents','forensic_events')
ORDER BY table_name, ordinal_position;
SELECT id,mmsi,ts,received_at,sog,lat,lon FROM vessel_tracks
WHERE mmsi='636019532'
  AND ts >= TIMESTAMP '2026-10-28 09:30:00'
  AND ts < TIMESTAMP '2026-10-28 11:30:00'
ORDER BY ts,id LIMIT 257;
ROLLBACK;
```
A returned 257 rows would exceed the 256-row complete-context cap. No fabricated query results.

## Release gate and next step

No production deploy, database write, incident promotion, historical correction, VM cron/timer/loop or new automation. Next: secure an explicitly authorized Oracle READ ONLY role; verify event/publication/receipt chronology and original vessel tracks; certify a reviewed pair of independent originating witnesses, then exercise the attack-only PLAY projection and human promotion review. A staging CI success alone is not proof of production correctness.
