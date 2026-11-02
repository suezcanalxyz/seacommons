# SeaCommons attack correlation — immutable lifecycle updates and read-only audit

Checked 2026-11-02 approximately 22:20–22:25 UTC. Branch `feature/maritime-attack-correlation-20261030`. Previous reported head: `eab7fb66`. Scope: GitHub staging branch, disposable isolated checkout for tests, authorized read-only Oracle queries and public API/source HTTP checks. **No production deploy, Oracle write, data deletion, historical rewrite, incident promotion, or VM scheduler.**

## Implemented

New `apps/api/core/intel/maritime_attack_staging_lifecycle.py`: metadata-only, deterministic, immutable review snapshots for status updates to an **existing** attack/piracy candidate. UPDATE02 cannot create a new attack, certify an independent original witness, infer an attacker, or promote to PLAY/LIVE. Source URL must be approved official HTTPS host and the same source document as the original. Report identity, publication boundary, source rights, update ID, event/receipt/publication/effective clocks and SHA-256 syntax are validated. Missing liberation time stays null. A complete selected-evidence digest changes when the snapshot metadata changes. No network, DB, or scheduler side effects.

New `tests/test_maritime_attack_staging_lifecycle.py`: 15 focused tests, including AZINI UPDATE02, replay/idempotent digest, UPDATE01/02 version separation, report and URL conflicts, lookalike hosts, invalid chronology, publication bypass, false independence, invented coordinates/attacker and invalid hashes.

Commits: `f3efb846` (module), `caab4717` (tests), `ba5ff56d` (Python 3.8 compatibility fix). Isolated shallow checkout of `ba5ff56d`: Python 3.12 stdlib unittest **15 lifecycle + 33 existing lineage = 48 passed**; Ruff **all checks passed**. Python 3.8 also passed all 15 lifecycle tests. A wider pytest suite was not run: offline uv cache lacked pytest. No new GitHub Actions status was returned for the new head; do not claim CI green for this revision.

## Verified case: MSCIO 161/26 / AZINI

Primary URL: https://mscio.eu/alerts/197 . On 2026-11-02, page contains UPDATE02: Operation ATALANTA confirms Iranian fishing vessel AZINI liberated and incident considered closed. Original hijacking reported for 2026-10-29 around 09:00 UTC. The source page displays Nov 2, 2026, 8:52 p.m. but does not explicitly identify that displayed time as UTC or state the **effective time of liberation**. Both effective and exact UTC publication clocks remain **null**. Later reported vessel coordinates are not the hijacking location. `MSCIO:161/26:UPDATE02` is a lifecycle evidence version, **not** a new attack or independent corroboration. MSCIO reuse rights are restricted; preserve metadata and source URL rather than mirroring content.

Other candidates still under review: MSCIO 164/26 and UKMTO 191/26 may share a single VHF Mayday origin on 2026-11-01 ~15:09 UTC (https://mscio.eu/alerts/200); UKMTO 192/26 is a separate late-1-November reported strike with original document not authenticated; CONTSHIP JET on 28 Oct (https://www.mod.bg/news9664), CHELSEA-3 and HS DIGNITY on 13 Oct (Bulgarian transport ministry), MSCIO 148/26 on 16 Oct (https://mscio.eu/alerts/184). None promoted or attributed to an aggressor without proof.

## Oracle PostgreSQL read-only audit

The authorized application connection used `PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=6000`, `BEGIN TRANSACTION READ ONLY`, and `ROLLBACK`. `transaction_read_only=on` verified. Queries use ISO string comparison for varchar time fields; native timestamp comparisons against `humanitarian_incidents.last_update_at` and `source_observations.observed_at` initially produced type errors and were rerun correctly.

| Table / metric | Previous | Current 72-hour rolling window |
|---|---:|---:|
| intel_events.timestamp_utc | 10,632 | 10,630 |
| vessel_tracks.ts | 817,358 | 818,600 |
| alert_events.timestamp_utc | 0 | 0 |
| anomaly_events.timestamp_utc | 0 | 0 |
| humanitarian_incidents.last_update_at | 12 | 12 |
| forensic_events.timestamp_utc | 10 | 10 |
| source_observations.observed_at | 50,569 | 50,691 |

The 72h window was evaluated around 2026-11-02 22:22 UTC; moving-window deltas are not net new rows. `source_observations WHERE observation_type='official_maritime_bulletin'` remains **0 total**. October `maritime_episodes` with `episode_family IN ('attack','piracy','explosion','sinking')` remains **0**. `pg_database WHERE datname LIKE '%_staging'` returns **0**. No authorized dedicated staging DB, hence no real PostgreSQL INSERT/rollback/replay certification.

Regression: `vessel_tracks WHERE mmsi='636019532' AND ts >= '2026-10-28' AND ts < '2026-10-29'` returns **9 rows**. CONTSHIP JET IMO 9348625, test event 28 Oct 10:00 UTC; earlier verified SOG 10.2 kn at 09:59:22 and 0.6 kn at 10:34:46, not re-read in this run. Bulgarian MOD report describes the strike and rescue but does not print IMO/MMSI. AIS slowdown is contextual, not independent proof; no attacker attribution.

## LIVE / PLAY

Read-only public endpoints: https://api.seacommons.org/api/v1/ .

`play/counts`: **3,588** total (132 humanitarian / 3,456 maritime), generated_at `2026-11-02T21:22:51Z`; page scan slightly later: eight HTTP 200 pages, **3,589 returned rows, 3,583 unique IDs, 6 duplicates**. No attack/piracy/sinking/explosion classification in inspected category fields. The count discrepancy and duplicates show offset pagination is **not snapshot consistent**.

`live/signals?mode=maritime&days=3&limit=500`: **14** (11 ais_anomaly, 3 vessel_incident), up from 12 in previous run; no attack-classified signal in returned types. `live/pipeline`: AIS live, first-party live, public feeds live, radio live, partner degraded. Radio DSC accepted **65**, NAVTEX accepted **0**.

## Source reachability from authorized VM

One-shot `curl -L --max-time 6`, HTTP response times only, **not** event-to-ingestion latency:

| Source | HTTP | Time |
|---|---:|---:|
| Bulgarian MOD news9664 | 200 | 485 ms |
| Bulgarian VTMIS NAVWARN | 200 | 207 ms |
| Bulgarian Transport homepage | 200 | 426 ms, redirect |
| MSCIO 161/26 | 200 | 336 ms |
| MSCIO 164/26 | 200 | 286 ms |
| UKMTO | 403 | 55 ms |
| MARAD | 403 | 28 ms |
| NATO Shipping Centre | 403 | 35 ms |
| IMO | 200 | 153 ms |
| ONI | 403 | 25 ms |
| GDELT DOC API | timeout / HTTP 000 | 6,001 ms |

Rights: UKMTO OGL with conditions (https://www.ukmto.org/terms-and-conditions), MSCIO restricted republication (https://www.mscio.eu/terms-of-service/), Bulgarian MOD allows reproduction with attribution (https://www.mod.bg/news9664). Other sources' reuse rights not certified. HTTP 403 is not global unavailability; no access restrictions bypassed.

## Next gates

1. Provision a genuinely isolated, explicitly authorized PostgreSQL `*_staging` DB and append-only role; run real insert, rollback, replay, corruption tests without production writes.
2. Wire lifecycle evidence to append-only staging snapshots and authenticated reviewer decisions. Keep original event and later status updates separate, with complete provenance.
3. Fix snapshot-consistent PLAY pagination and canonical official-source acquisition, while requiring **two verified independent original witness origins** for incident promotion.
4. Preserve distinct attack/piracy UI categories and colors, separate from humanitarian drift; never treat AIS gaps, sudden stops, or news republications as independent proof.
