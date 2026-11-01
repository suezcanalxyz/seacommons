# SeaCommons — deep relay lineage, incident candidates and LIVE/PLAY audit
Audit: 2026-11-01 19:26–19:28 UTC. Staging branch: `feature/maritime-attack-correlation-20261030`.
Previous head: `8d8bdbe19060bc8b5e0704123379f25cf8cc599a`.

## Code change and certified tests
- `apps/api/core/intel/maritime_attack_correlation.py`: `_lineage_components.find` now uses an iterative walk with path compression. A descending 1,601-edge reviewed syndication chain previously could exceed Python's recursion limit during correlation. This is a correctness/safety fix: the long chain must remain ONE originating lineage, never 1,601 independent reports.
- `tests/test_maritime_attack_lineage_scaling.py`: three new synthetic regressions: 1,601-edge collapse, no false second witness, and an unrelated third original still independent. No assertion of real-world independent witnesses.
- Existing staging workflow extended to watch the new test file. No new workflow, cron, VM timer or deployment.
- CI GitHub Actions run `41341729343` on commit `51e8e8a1582d39dfde510aaa1df0b97ba43d6afc`: four jobs SUCCESS. Unit 333 PASS + official bulletin 19 PASS + SQLite 3 PASS + PostgreSQL isolated 6 PASS = **361 Python PASS**. Frontend 5 JavaScript PASS, Vite build SUCCESS. This is CI/staging only, not Oracle integration.
- Compare `8d8bdbe1...feature/maritime-attack-correlation-20261030`: 3 commits, 3 files, ahead 3, behind 0, at the point of functional CI. Report commit follows.
- No incident promotion. Correlator's `publication_allowed` remains false.

## Read-only LIVE/PLAY endpoints
Queried using the authorized remote device, HTTP GET only, at ~19:26 UTC:
- `https://play.seacommons.org/api/v1/play/counts` HTTP 200: `total_count=3575`, `maritime_count=3446`, `humanitarian_count=129`, `investigation_count=3435`; generated `2026-11-01T18:17:52.533981+00:00`.
- `https://play.seacommons.org/api/v1/play/incidents?limit=1` HTTP 200: `total_count=3576`; generated `2026-11-01T19:26:43.399342+00:00`. The **one-record discrepancy** reflects non-synchronous snapshots; do not assume persistent data corruption.
- `https://live.seacommons.org/api/v1/live/pipeline` HTTP 200: generated `2026-11-01T19:26:43.660170+00:00`; AIS, first-party, public feeds and radio `live`; partner `degraded`. Radio decoder `dsc_accepted=47`, `navtex_accepted=0`. The radio state is NOT proof that NAVTEX warnings are being ingested.
- `https://seacommons.org/api/v1/live/signals?mode=maritime` HTTP 200, nine maritime features. Attack category not end-to-end certified.
- HTTP response time is not source-event-to-ingestion latency. No latency claim for the underlying official sources.

## Candidate incidents (rolling 72h and October retrospective)
At 19:26 UTC, rolling 72h begins 2026-10-29 19:26 UTC.
- **MSCIO 159/26**: event 2026-10-29 22:12 UTC, ~25 NM northeast of Khasab, Strait of Hormuz; reported tanker, two explosive devices attached by a small boat, engine-room fire. Official notice published Oct 30: https://mscio.eu/alerts/195 . IMO/MMSI unverified. Single originating alert, not corroborated.
- **MSCIO 162/26**: event 2026-10-30 18:00 UTC, ~40 NM south of Lavan Island; vessel struck on port side, fire. Official notice published Oct 30: https://mscio.eu/alerts/198 . IMO/MMSI unverified. Do not merge with AL MAYEDA solely on region and date.
- **AL MAYEDA**, IMO 9397298, reported MMSI 538003356: operator Nakilat reported unidentified objects striking the LNG carrier evening Oct 30, exact UTC/coordinates and weapon unknown. Operator URL https://nakilat.com/al-mayeda-vessel-incident-in-the-arabian-gulf/ previously identified; not independently retrievable in this run. Qatar government response may derive from operator. No aggressor attribution.
- **CONTSHIP JET**, IMO 9348625, MMSI 636019532: 2026-10-28 ~10:00 UTC, retrospective outside 72h. Bulgarian Ministry of Defence https://www.mod.bg/news9664 directly describes three impacts and rescue but does not contain IMO/MMSI. Contships operator https://contships-management.com/2026/10/29/contships-management-inc-company-update/ provides IMO and a relayed Master's statement; not an authenticated original witness artifact. AIS speeds 10.2 knots at 09:59:22 and 0.6 knots at 10:34:46 UTC are context, not independent attack evidence. Separate sinking consequence must not be counted as a second attack.
- **MSCIO 158/26**, event Oct 29 16:00 UTC: outside rolling 72h, remains October retrospective. **AZINI / MSCIO 161/26**, Oct 29: alleged hijacking; later location is not automatically the incident site.
- Official context: MARAD 2026-012 https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-of-azov-military-combat-operations (active to 2027-03-22); this is risk context, not individual incident corroboration.
- GDELT Project DOC 2.0 direct request for CONTSHIP JET/AL MAYEDA in 72h returned HTTP **429**; no results ingested, no rate-limit bypass or retry loop. GDELT Project public DOC API must not be confused with the separately priced GDELT Cloud product. Source publication-to-collector latency remains unmeasured.

## Oracle PostgreSQL read-only status
Authorized remote device online; prior database access fails `FATAL: role "ubuntu" does not exist`. No new privileged or credential-discovery attempts. **New Oracle SQL queries executed: zero.** These are PREPARED ONLY:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '6000ms';
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('intel_events','vessel_tracks','alert_events',
                     'anomaly_events','humanitarian_incidents','forensic_events')
ORDER BY table_name, ordinal_position;
SELECT id, mmsi, ts, received_at, sog, lat, lon
FROM vessel_tracks
WHERE mmsi='636019532'
  AND ts >= TIMESTAMP '2026-10-28 09:30:00'
  AND ts < TIMESTAMP '2026-10-28 11:30:00'
ORDER BY ts,id LIMIT 257;
ROLLBACK;
```
A result of 257 rows means the 256-row bound was exceeded and the trajectory is incomplete. After schema inspection, separate bounded read-only audits are needed for the rolling 72h and October in the six operational tables. No record history was changed.

## Rights, evidence and release gates
- Bulgarian MoD page explicitly permits copying public information with attribution; does not automatically cover third-party media.
- MSCIO/IMO/operator/Reuters and commercial registry bulk reuse is not established; only factual metadata and links are included.
- Two publishers or mirrored URLs do not imply two original independent witnesses. Provenance must preserve source URL, original report ID, captured hash, event time, publication time, receipt time, and operator review.
- No perpetrator attribution without separate evidence. AIS gap/sudden stop never establishes an attack.
- Next: obtain authorized Oracle read-only role, validate receipt clocks and six-table schema; certify reviewed source lineage and the PLAY attack-specific UI/category through staged API tests. Production deployment requires explicit approval.
