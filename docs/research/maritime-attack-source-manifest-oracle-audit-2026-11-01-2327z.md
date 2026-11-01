# SeaCommons — source-faithful maritime attack staging audit
**Audit window:** 2026-11-01 23:20–23:28 UTC. **Branch:** `feature/maritime-attack-correlation-20261030`. **Baseline:** `2d69d948`. **Tested functional HEAD:** `26b540ac`. No production deploy.

## Material change this run

The existing isolated staging pipeline now has a bounded, metadata-only six-document source-check manifest. It can be validated without network or DB access, and the existing canonical `ingest_official_bulletin` writer is exercised with all six records in a disposable PostgreSQL 16 GitHub Actions service. The transaction is rolled back and no public `IntelEvent` or `MaritimeEpisode` is created. This is **not** a live source collector and is **not** an Oracle import.

1. Corrected a factual provenance error in three older test suites: the actual Bulgarian MOD `news9664` release names CONTSHIP JET but **does not state IMO 9348625 or MMSI 636019532**. Those identifiers must remain separate reviewed identity evidence. Synthetic identified-ship tests now use an explicitly synthetic source record. A new isolated PostgreSQL regression verifies the source-faithful name-only bulletin → immutable `SourceObservation` → external IMO/MMSI crosswalk → candidate-only correlation.
2. Added `event_time_approximate` and optional *documented* `reported_time_uncertainty_minutes` to the existing official bulletin adapter. A source reporting "approximately 22:12 UTC" retains the reported time and an `approximate` precision label; without a defensible numeric bound the correlator enforces **1440 minutes** of uncertainty, preventing precision-qualified automatic corroboration. Original source ID hashes for existing non-approximate bulletins remain unchanged.
3. Added `maritime_attack_staging_manifest.py`, with strict official-host validation, bounded batches, canonical URL deduplication, source-rights status, chronology and source-date validation, no automatic origin verification, and a specific guard against smuggling IMO/MMSI into the original MOD `news9664` record.
4. Added a metadata-only source-check file, `maritime-attack-source-check-2026-11-01.json`, containing Bulgarian MOD news9664 and MSCIO 158/26, 159/26, 160/26, 161/26, 162/26. All six are candidate observations, not six independently corroborated attacks. The MSCIO 160/26 approach is explicitly `suspicious_activity`, a negative attack-control. MSCIO 161/26 is `piracy`; subsequent AZINI positions are not treated as the hijacking site.
5. Added unit and isolated PostgreSQL integration tests. Existing staging CI workflow is extended; no new workflow schedule, cron, VM timer or poller.

## CI

GitHub Actions run `41362168992`, commit `26b540ac`: all four jobs **SUCCESS**. Python: 352 maritime attack tests, 21 official bulletin tests, 3 isolated SQLite tests, 8 isolated PostgreSQL tests = **384 passing**. JavaScript: **5 passing**, Vite frontend build **SUCCESS**. The PostgreSQL service is disposable and has no Oracle credentials.

## Oracle production audit — read-only, no mutations

Read-only queries used `PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=4500'` with the application's existing authorized DB connection. They did not create or alter roles, tables, records, jobs or files.

Reference query shapes (executed individually, with bounded output):
```sql
SELECT count(*) FROM intel_events WHERE timestamp_utc >= '2026-10-29T23:21:00';
SELECT count(*) FROM vessel_tracks WHERE ts >= (now() AT TIME ZONE 'UTC') - interval '72 hours';
SELECT count(*) FROM alert_events WHERE timestamp_utc >= '2026-10-29T23:21:00';
SELECT count(*) FROM anomaly_events WHERE timestamp_utc >= '2026-10-29T23:21:00';
SELECT count(*) FROM humanitarian_incidents WHERE updated_at >= (now() AT TIME ZONE 'UTC') - interval '72 hours';
SELECT count(*) FROM forensic_events WHERE timestamp_utc >= '2026-10-29T23:21:00';
SELECT source_name, count(*) FROM source_observations
 WHERE observed_at >= '2026-10-01' AND observed_at < '2026-11-02'
   AND observation_type IN ('official_maritime_bulletin', 'operator_incident_statement')
 GROUP BY source_name;
SELECT episode_family, count(*) FROM maritime_episodes GROUP BY episode_family;
SELECT id, mmsi, ts, received_at, sog, lat, lon FROM vessel_tracks
 WHERE mmsi='636019532'
   AND ts >= '2026-10-28 09:30:00' AND ts < '2026-10-28 11:30:00'
 ORDER BY ts, id LIMIT 25;
```

Results around 23:21 UTC (last 72-hour window is a moving boundary): **9,710** intel events, **798,539** vessel tracks, **0** alert events, **0** anomaly events, **21** recently updated humanitarian incidents (not necessarily new distress), **11** forensic events. There were **zero** canonical `official_maritime_bulletin`/`operator_incident_statement` observations in the checked October-to-November range and **zero** `attack_episode`/`maritime_attack_episode`/`maritime_attack` families. Existing episode families include rendezvous, AIS gaps, spoofing and safety; none should be reclassified from their name alone.

**CONTSHIP JET** `vessel_tracks` samples:
- 2026-10-28 09:57:55 UTC — 10.8 kn, 43.26831 N, 28.8189467 E;
- 09:59:22 UTC — 10.2 kn, 43.2659267 N, 28.8149000 E;
- 10:34:46 UTC — 0.6 kn, 43.2591967 N, 28.8157400 E;
- 10:46:24 UTC — 0.7 kn;
- 10:58:15 UTC — 0.8 kn.

These are contextual AIS observations, not independent proof of attack or attribution. In these legacy rows `received_at == ts`; do not claim to have measured real collector latency from them.

The first count queries against `timestamp_utc` failed because these columns are VARCHAR, not PostgreSQL timestamps; the audit was corrected to compare canonical ISO timestamp strings. Failed queries were not presented as measurements.

## LIVE/PLAY and source availability

At ~23:25 UTC, public PLAY counts returned **3,576** (3,447 maritime, 129 humanitarian). A complete paginated scan of **all 3,576** PLAY incidents found **zero** attack-labeled items. The LIVE signals endpoint for three days returned **11** signals and **zero** attack-labeled items. HTTP 200 does not imply the new staging source adapter is deployed. LIVE pipeline: AIS, first-party and public feeds `live`, partner `degraded`, radio `live`, but `navtex_accepted=0` and `dsc_accepted=47`. NAVTEX acquisition is not demonstrated. PLAY counts are cached and not transactionally synchronized with catalog queries.

Official links checked:
- Bulgarian Ministry of Defence, `news9664`: https://www.mod.bg/news9664 — names CONTSHIP JET, describes three observed strikes and crew rescue. The site allows public copying with explicit source attribution. HEAD from Oracle: **200**, ~507 ms.
- MSCIO `159/26`: https://mscio.eu/alerts/195 — attack report, approximately 29 Oct 22:12 UTC, 25 NM NE Khasab; vessel unnamed. HEAD **200**, ~294 ms.
- MSCIO `162/26`: https://mscio.eu/alerts/198 — attack report, approximately 30 Oct 18:00 UTC, 40 NM south of Lavan; vessel unnamed. HEAD **200**, ~223 ms.
- MSCIO `160/26`: https://mscio.eu/alerts/196 — suspicious approach without shots or boarding. Negative control.
- MSCIO `161/26`: https://mscio.eu/alerts/197 — reported AZINI hijacking; later positions are not event-site coordinates.
- UKMTO: https://www.ukmto.org/ — recent notices #187 and #188 plausibly overlap MSCIO 159/26 and 162/26, respectively. Treat these as potentially **shared upstream reports**, not independent witnesses.
- MARAD: https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations — active regional risk advisory, not a witness to CONTSHIP JET.
- ONI: https://www.oni.navy.mil/ONI-Reports/Shipping-Threat-Reports/Worldwide-Threat-to-Shipping-WTS/ — public historical shipping-threat reports, not a minute-level incident feed.

Direct HEAD **and** limited GET from Oracle returned **403** for UKMTO, MARAD and ONI. They are accessible via public search/web but **not currently retrievable from this Oracle VM route**; do not bypass their access controls. MSCIO and MOD responded. The 223–507 ms measurements are **HTTP request latency**, not publication-to-SeaCommons ingestion delay. GDELT previously returned HTTP 429 and was not retested this run.

MSCIO is conservatively marked `restricted_republication` pending explicit reuse clearance; the manifest contains source URLs and metadata, not copied alert text. No automated import or redistribution of restricted full text occurred.

## Open gates and next action

**Critical unresolved gate:** the source-checked six-item manifest exists on the branch and is proven to write to an isolated, rolled-back PostgreSQL database, but it has **not** been ingested into Oracle or an operational staging DB. Thus production LIVE/PLAY still have **zero attack incidents**. To connect the pipeline safely, use an explicitly authorized isolated staging database and an operator-reviewed source/identity manifest, then test canonical `SourceObservation` → reviewed extraction → verified origin lineage → `MaritimeEpisode` candidate → public PLAY projection under `publication_allowed=false`. Do not count AIS speed changes or duplicate UKMTO/MSCIO bulletins as second witnesses. Verify UI attack color separately from humanitarian distress/drift.

No production deployment, no historical updates, no deletions, no incident promotions, no VM cron/timer/loop/scheduler changes. No attacker attribution.
