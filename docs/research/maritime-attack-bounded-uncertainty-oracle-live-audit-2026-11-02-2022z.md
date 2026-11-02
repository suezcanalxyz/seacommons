# SeaCommons maritime attack correlation — bounded temporal uncertainty and read-only audit
Date: 2026-11-02, ~20:22–20:30 UTC. Branch: `feature/maritime-attack-correlation-20261030`.

## Changes since previous run
Previous functional head: `e2be004c835c55abc302dafbf8a4ebbfb3e149ae`. New tested functional commit: `3c1d8a2f8f80ce25d9b80541239cd4a5ce06f82d`.

Changed files:
- `apps/api/core/intel/maritime_attack_staging_lineage.py`
- `apps/api/core/intel/maritime_attack_staging_manifest.py`
- `tests/test_maritime_attack_staging_lineage.py`
- `tests/test_maritime_attack_staging_manifest.py`

The staging-only correlator now validates source-declared `reported_time_uncertainty_minutes` (positive, finite, <=1440, and only for approximate clocks). Unknown uncertainty contributes **zero** automated temporal allowance. For an explicitly documented approximate clock, a publication/receipt a few minutes before the *nominal* event timestamp can be chronologically possible if within the stated interval; an earlier publication outside that interval is rejected. For suspected shared-origin links, source-declared bounds may extend the existing 120-minute compatibility window by **at most 120 additional minutes**; a bound exceeding 120 minutes blocks the proposed link for manual review. This changes only candidate clustering, **never** independent-witness verification or publication permission. Vessel identity and geographic conflict checks remain mandatory. Day-only dates remain day-only.

Regressions include approximate publication before nominal time, missing bound, malformed/negative/NaN/infinite bounds, broad uncertainty, a candidate near the edge of the temporal window, and conflicting IMO despite temporal overlap. No source origin, attacker or geometry is inferred.

**Tests:** `PYTHONPATH=apps/api apps/api/.venv/bin/python -m unittest discover -s tests -p 'test_maritime_attack*.py' -q`: **463 tests PASS** in a disposable checkout. `ruff check` on the four changed files PASS; `git diff --check` PASS. GitHub Actions run [41519015634](https://github.com/suezcanalxyz/seacommons/actions/runs/41519015634): **SUCCESS**, all four jobs (correlation-unit, bulletin-writer-postgres, bulletin-writer-sqlite, frontend-attack-taxonomy).

## Oracle PostgreSQL audit — strictly read-only
Read from the existing application connection with PostgreSQL `default_transaction_read_only=on`, `statement_timeout=6000`, `connect_timeout=5`; verified `SHOW transaction_read_only = on`. Queries ran in an explicit transaction, ended with rollback. No DDL, write, schema creation, or historical update.

72h rolling window starts `2026-10-30T20:22:33Z` (UTC). SQL shapes:
```sql
SELECT count(*) FROM intel_events WHERE timestamp_utc >= :start;
SELECT count(*) FROM vessel_tracks WHERE ts >= CAST(:start AS timestamptz);
SELECT count(*) FROM alert_events WHERE timestamp_utc >= :start;
SELECT count(*) FROM anomaly_events WHERE timestamp_utc >= :start;
SELECT count(*) FROM humanitarian_incidents WHERE last_update_at >= :start;
SELECT count(*) FROM forensic_events WHERE timestamp_utc >= :start;
SELECT count(*) FROM source_observations WHERE observation_type = 'official_maritime_bulletin';
SELECT count(*) FROM maritime_episodes
 WHERE start_at >= '2026-10-01' AND start_at < '2026-11-01'
 AND episode_family IN ('maritime_attack','piracy','explosion','sinking');
```

| Relation | Prior rolling window | This run |
|---|---:|---:|
| intel_events by event timestamp | 10,608 | 10,638 |
| vessel_tracks | 815,276 | 816,255 |
| alert_events | 0 | 0 |
| anomaly_events | 0 | 0 |
| humanitarian_incidents by last_update_at | 15 | 12 |
| forensic_events | 8 | 10 |
| official_maritime_bulletin (all time) | 0 | 0 |
| October canonical attack/piracy/explosion/sinking episodes | not newly certified | 0 |

These are **rolling-window counts**, not net new insertions. `intel_events.timestamp_utc` is varchar ISO 8601 and compared lexically; native typed timestamps are preferable for permanent audits. Top recent `intel_events` categories are AIS anomaly, AIS spike, correlated alert, rendezvous and navigation events; a bounded title-keyword search returned **zero** ship/tanker attack candidates in the last 72h and October. This does not mean there were no real attacks.

The only connectable PostgreSQL databases listed by the existing role are `postgres` and `seacommons`. `attack_review_staging` schema is absent; no authorized dedicated `*_staging` database is present. The append-only staging store therefore remains **code-only**, with no live persistence test.

## CONTSHIP JET regression (28 October, 10:00 UTC)
Read-only query:
```sql
SELECT ts, sog FROM vessel_tracks
WHERE mmsi = '636019532'
 AND ts >= '2026-10-28 09:45:00+00'
 AND ts <= '2026-10-28 11:10:00+00'
ORDER BY ts LIMIT 15;
```
Returned five AIS fixes: 09:57:55 (10.8 kn), 09:59:22 (10.2 kn), 10:34:46 (0.6 kn), 10:46:24 (0.7 kn), 10:58:15 (0.8 kn). The primary [Bulgarian Ministry of Defence report](https://www.mod.bg/news9664) documents the drone attack at 12:00 local time / 10:00 UTC and three impacts, with 18 crew rescued. The slowdown is contextual, **not** independent proof. IMO 9348625 and MMSI 636019532 come from the regression vessel identity, not from the ministry article; do not claim the ministry published these identifiers. The later sinking remains a distinct outcome.

## Public LIVE/PLAY — read-only HTTP
- `GET /api/v1/play/counts`: HTTP 200; `total_count=3585`, `humanitarian_count=130`, `maritime_count=3455`, `investigation_count=3447`.
- Eight pages of `GET /api/v1/play/incidents?limit=500&offset=...`: HTTP 200; **3,588 returned rows, 3,582 distinct IDs, six duplicate rows**, no attack/piracy/sinking/explosion category in returned rows. The count/scan mismatch and duplicates confirm **non-snapshot-consistent pagination**. Do not infer exhaustive coverage.
- `GET /api/v1/live/signals?days=3&limit=300&mode=all`: HTTP 200; **13 features** (10 `ais_anomaly`, two `vessel_incident`, one `twitter`), zero attack-classified.

## Candidate incidents and source dependency
- **MSCIO 164/26**, Strait of Hormuz, 2026-11-01 ~15:09 UTC, VHF Channel 16 Mayday relay; vessel unknown. [MSCIO notice](https://mscio.eu/alerts/200). **UKMTO 191/26** appears to relay the same Mayday and cannot be counted as an independent witness without original-report lineage.
- **UKMTO 192/26**, 2026-11-01 23:47 UTC, tanker reportedly hit by two unknown projectiles ~72 NM east of Ras Al Khafji. Original UKMTO PDF not acquired directly; [secondary report](https://regulasshipping.com/blog/ukmto-192-26-records-a-tanker-projectile-hit-72-nm-east-of-ras-al-khafji/). Separate from 191/26; vessel name/IMO/MMSI/precise point unknown. No promotion.
- **MSCIO 148/26**, 2026-10-16 ~19:22 UTC, tanker RPG incident ~78 NM northeast of Al Jubayl, [official notice](https://mscio.eu/alerts/184). No hull ID or precise coordinates; remains staging-only.
- **CHELSEA-3 and HS DIGNITY**, 2026-10-13 Black Sea, [Bulgarian Transport Ministry](https://www.mtc.government.bg/). Distinct cases. AIS loss on HS DIGNITY is a contextual signal, not proof.
- **CONTSHIP JET**, 2026-10-28, [Bulgarian Defence Ministry](https://www.mod.bg/news9664). Separate attack and subsequent sinking; no attacker attributed.
- **LOUISE 1** is a retrospective media lead from [Reuters, 30 October](https://www.reuters.com/world/tanker-strait-hormuz-hit-by-limpet-mines-security-sources-say-2026-10-30/); its naming is attributed to security sources, not directly verified against the original UKMTO notice. No canonical manifest created from a secondary identification.

## HTTP availability from Oracle VM (one-shot requests, not ingest latency)
| Source | Result | Approx. response time |
|---|---|---:|
| Bulgarian Defence Ministry report | URL error/timeout | 7,215 ms |
| Bulgarian Transport Ministry | HTTP 200 | 574 ms |
| VTMIS NAVWARN | HTTP 200 | 312 ms |
| MSCIO 164/26 | HTTP 200 | 306 ms |
| MSCIO 148/26 | HTTP 200 | 239 ms |
| UKMTO | HTTP 403 | 61 ms |
| MARAD 2026-012 | HTTP 403 | 32 ms |
| NATO Shipping Centre | HTTP 403 | 133 ms |
| IMO | HTTP 200 | 221 ms |
| ONI | HTTP 403 | 29 ms |
| GDELT DOC API | URL error/timeout | 7,143 ms |

An HTTP 200 proves reachability only, not a permitted ingestion feed or independent eyewitness; HTTP 403 was not bypassed. Source publication-to-receipt latency cannot be calculated without durable ingestion receipts. UKMTO publishes under [Open Government Licence](https://www.ukmto.org/terms-and-conditions) with conditions; [MSCIO](https://www.mscio.eu/terms-of-service/) has redistribution restrictions. Bulgarian Defence Ministry permits copying with attribution on its page. [MARAD 2026-013](https://www.maritime.dot.gov/msci/2026-013-red-sea-bab-el-mandeb-strait-gulf-aden-arabian-sea-and-somali-basin-houthi-attacks) advises that disabling AIS may be a safety measure in some threat areas: **AIS gaps cannot prove attack**. [MARAD 2026-012](https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations) documents Black Sea shipping hazards.

## Blockers and next action
1. Provision and explicitly authorize an **isolated** `*_staging` PostgreSQL database with a non-owner INSERT/SELECT-only role, then test insert, rollback, re-read, replay/idempotence and immutable audit history there. Do not use production Oracle DB.
2. Verify original UKMTO PDFs, document source rights and original witness dependency. Do not count MSCIO and UKMTO republishing the same Mayday as two witnesses.
3. Add authenticated manual review and controlled PLAY → maritime incident promotion only after independently corroborated evidence, preserving separate incident colors from humanitarian drift. No production deployment without explicit approval.

**Safety:** no new cron, timers, background loops or VM scheduling; no production deploy, no Oracle write, no deletions, no changes to historical records, no promoted incident.
