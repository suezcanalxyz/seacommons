# SeaCommons — Operator witness relay guard and maritime incident correlation audit
Date: 2026-11-01 ~16:26 UTC (17:26 Africa/Tunis). Staging branch: `feature/maritime-attack-correlation-20261030`.
Previous baseline: `6538b534`. No production deployment, VM cron/timer/loop, Oracle mutation, or historical rewrite.

## Implemented: source-faithful operator witness relay
The 29 October Contships Management company update (datelined Athens, 28 October) names **CONTSHIP JET, IMO 9348625**, and reports three sea drones and a statement made by the Master. The published page does **not** contain an original, separately authenticated Master's transcript, a verifiable exact publication clock, an exact incident clock, or MMSI 636019532. It cannot be counted as a verified independent first-hand witness simply because the manager quotes the Master.

New pure module `apps/api/core/intel/maritime_attack_operator_statement.py` creates a metadata-only `operator_incident_statement` envelope. It preserves the event date (2026-10-28), publication date (2026-10-29), original source URL, vessel name, IMO, unknown MMSI, and optional *actually observed* receipt timestamp. Its `observed_at` is explicitly labelled **publication** rather than a fabricated event timestamp. It stores no coordinates for the approximate offshore area. Original witness artifact, independence, reuse rights, and attack corroboration are all **unverified/false**. No ingestion, scheduler or database writes are introduced.

`apps/api/core/intel/maritime_attack_correlation.py` now treats this observation type as source-bound: extracted vessel IDs cannot be invented, the incident date must match the original document, day-only event time uncertainty is at least **1440 minutes** even when an extraction proposes zero, and an approximate position cannot be laundered into an exact incident site. Even if a caller sets `origin_authority_verified=true`, an operator relay **cannot supply an independent attack source group**. It can be retained as a candidate for human review but cannot be used as the second independent witness.

Six offline regressions added in `tests/test_maritime_attack_operator_statement.py`: source-faithful dates/identity; allowed source origin; malformed IDs and reversed chronology; actual receipt clocks; forged exact time/IMO/MMSI/coordinates; and a synthetic ministry+manager+AIS case that stays `candidate` even when a provenance flag is incorrectly set. CI path filters updated so this test runs on staging pushes.

Commits after `6538b534`:
- `5d14136f` — operator metadata-only relay envelope.
- `d1c16e51` — source-bound operator extraction, day precision and no automatic independence.
- `05cf61cd` — six regression tests.
- `6e245d53` — CI path filters.

## CI verified
GitHub Actions run https://github.com/suezcanalxyz/seacommons/actions/runs/41326222531 completed **SUCCESS** on `6e245d53`, all four jobs green.
- Correlation-unit: 314 tests PASS (including six new operator witness tests).
- Official bulletin adapter: 19 PASS.
- SQLite writer: 3 PASS.
- Isolated PostgreSQL 16 writer: 6 PASS.
- Total: **342 Python PASS**.
- Frontend JS attack taxonomy: 5 PASS, frontend build SUCCESS.
These results are from isolated CI and do not prove Oracle production ingestion or PLAY promotion.

## Current source candidates, event time versus publication time
1. **CONTSHIP JET** (IMO 9348625, MMSI 636019532 from separate identity crosswalk): incident 2026-10-28 ~10:00 UTC in Bulgarian Black Sea. Ministry of Defence: https://www.mod.bg/news9664 (naval surveillance / French aircraft observations); operator: https://contships-management.com/2026/10/29/contships-management-inc-company-update/ (Master's account *reported by manager*). Two potentially distinct reporting origins, but **independence remains unverified**. Operator has no MMSI; do not attribute the identifier to its statement. AIS deceleration is context, not attack proof.
2. **MSCIO 159/26**, 2026-10-29 22:12 UTC, Strait of Hormuz: https://mscio.eu/alerts/195 ; Reuters identifies LOUISE 1 through maritime security sources, not a direct IMO/MMSI crosswalk. UKMTO relay may share source lineage.
3. **MSCIO 162/26**, 2026-10-30 18:00 UTC, Gulf region: https://mscio.eu/alerts/198 ; vessel identifiers unknown.
4. **AZINI / MSCIO 161/26**, 2026-10-29: https://mscio.eu/alerts/197 ; AP reported Puntland police account on 2026-11-01 https://apnews.com/article/dd4d404235781a3b871668c353540e4c . Source independence and incident site not certified.
5. **Qeshm two fishing boats**, 2026-10-31, Reuters attributed allegation to Iranian sources: https://www.reuters.com/world/middle-east/iran-provincial-official-says-us-attacked-fishing-boats-off-qeshm-island-state-2026-10-31/ . No vessel IDs or verified attacker; no promotion.
6. **Negative control:** Reuters 2026-11-01 report of alleged radio harassment of shipping off Taiwan: https://www.reuters.com/world/china/taiwan-says-china-harassing-shipping-with-east-coast-patrol-2026-11-01/ . This is not a documented physical ship attack and should not enter attack family.
7. **October retrospective IMO**: https://www.imo.org/en/mediacentre/hottopics/pages/middle-east-highlighted-incidents.aspx (122 confirmed incidents as at 2026-10-30); do not infer independent origin relative to MSCIO/UKMTO or treat same IMO on different dates as one event.

New source nuance: charterer ZIM's 28 October customer update https://www.zim.com/za-hant/customer-updates/mv-contship-jet-cj5-v-74w shows “06:15” on one locale, with timezone unclear. It says the owners informed the charterer; this is **a derivative relay**, not a third original eyewitness. Never treat the site's display time as the incident time or as an independent attack report.

## Read-only LIVE/PLAY check (authorized remote device, 16:23–16:26 UTC)
- PLAY counts GET: HTTP 200; total **3573**, maritime **3445**, humanitarian **128**, investigation **3435**; generated_at `2026-11-01T16:23:40.080798Z`.
- PLAY incidents?limit=1 GET: HTTP 200; total **3575**; generated_at `2026-11-01T16:25:46.963783Z`.
- LIVE pipeline GET: HTTP 200; generated_at `2026-11-01T16:25:47.058388Z`; AIS, first-party, public feeds and radio live, partner degraded. Radio decoder `navtex_accepted=0` despite `accepted=46` DSC messages.
The two PLAY projections differ by **two records** and by approximately two minutes of generation time. They are not synchronized snapshots. HTTP 200 does not certify new attack-family rendering or end-to-end promotion.

## Oracle PostgreSQL read-only limitation
Authorized remote device is online, PostgreSQL command present. `psql -X -w -Atqc 'SHOW transaction_read_only'` returned `FATAL: role "ubuntu" does not exist`. No credential discovery, privilege changes, or writes attempted. **Fresh SQL results: zero**. No current claims about `intel_events`, `vessel_tracks`, `alert_events`, `anomaly_events`, `humanitarian_incidents`, `forensic_events`, or `maritime_episodes` row counts.

Prepared, **not executed**, SQL after a valid approved read-only role is available:
```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '6000ms';
SELECT id, mmsi, ts, received_at, sog, lat, lon
FROM vessel_tracks
WHERE mmsi = '636019532'
  AND ts >= TIMESTAMP '2026-10-28 09:30:00'
  AND ts <= TIMESTAMP '2026-10-28 11:30:00'
ORDER BY ts, id LIMIT 257;
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('intel_events','vessel_tracks','alert_events',
                     'anomaly_events','humanitarian_incidents','forensic_events')
ORDER BY table_name, ordinal_position;
ROLLBACK;
```
After schema inspection, choose each table's actual event and receipt clocks for 72-hour and October 2026 windows; never substitute publication for event time.

## Availability, rights and latency
- Bulgaria MoD page, Contships statement, ZIM update, MARAD 2026-012 https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations, IMO highlighted incidents, and MSCIO alerts were publicly discoverable during this audit.
- Ministry public text allows attributed reuse subject to its terms; Contships/ZIM materials remain copyrighted or subject to site terms. IMO restricts commercial reuse. No bulk copying or republication authorized.
- MARAD 2026-012 is a standing risk advisory, **not individual attack proof**. NAVAREA III and NATO Shipping Centre are referenced there, but their individual October warnings were not exhaustively verified in this run.
- The advertised 15-minute GDELT update interval is not SeaCommons ingestion latency; no measured end-to-end latency for these incident reports was obtained.
- Unknown original report receipt/publication clocks remain unknown. No aggressor attribution.

## Next gates
1. Obtain an approved read-only Oracle database role; verify CONTSHIP JET `received_at` and inspect all six requested tables plus episode/projection views.
2. Obtain a verifiable original Master account or independent original witness artifact and establish lineage before allowing any second-source corroboration.
3. Test a staging-only, fully traceable source → entity resolution → AIS context → human review → PLAY incident projection, including attack-specific UI color versus humanitarian drift, false positive/negative controls and snapshot consistency.
4. No production deployment without explicit approval.
