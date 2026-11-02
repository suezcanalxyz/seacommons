# SeaCommons — MSCIO 159/26 and 162/26, source-identity guard and read-only audit

Checked 2026-11-02 approximately 23:18–23:27 UTC, on isolated checkout of branch `feature/maritime-attack-correlation-20261030`. Previous reported head `e7f9955b`. Scope: source review, staging-only code, isolated offline tests, authorized **read-only** Oracle PostgreSQL and public LIVE/PLAY endpoints. No production deploy, database write, historical rewrite, incident promotion, scheduler, or VM cron.

## Newly reviewed primary-source candidates

1. **MSCIO:159/26** — https://mscio.eu/alerts/195 — event **2026-10-29 ~22:12 UTC**, 25 NM northeast of Khasab, Oman, Strait of Hormuz. MSCIO reports an unnamed tanker approached by a small boat, two devices attached to hull, explosions, engine-room fire and temporary loss of propulsion; crew safe and voyage resumed. Page publication displays **30 Oct 2026 07:44** with no explicit UTC timezone; manifest therefore records **publication_date=2026-10-30**, not an invented publication instant. UKMTO **187-26** appears to describe the same original incident; do **not** count MSCIO and UKMTO as independent eyewitnesses. Reuters, 30 Oct, attributes vessel name **LOUISE 1** to maritime security sources, but **MSCIO does not identify the vessel**. No IMO/MMSI or vessel name was imported into MSCIO primary-source metadata; secondary entity-resolution candidate requires separate evidence and review. No attacker attribution.
2. **MSCIO:162/26** — https://mscio.eu/alerts/198 — event **2026-10-30 ~18:00 UTC**, 40 NM south of Lavan Island, Arabian Gulf. Unnamed vessel reportedly struck on port side by an unknown projectile, onboard fire, crew safe; no environmental impact reported. Page displays **30 Oct 2026 22:17**, without an explicit timezone. Source-specific manifest stores day-only publication date. No name/IMO/MMSI or precise attack coordinates inferred. Separate event from 159/26.
3. Existing **MSCIO:163/26** — https://mscio.eu/alerts/199 — 28 Oct, day-only, Strait of Hormuz, already has a staging manifest; not duplicated here.
4. Latest-window priority remains **MSCIO:164/26** — https://mscio.eu/alerts/200 — 1 Nov ~15:09 UTC VHF Mayday relay, likely same reporting origin as UKMTO 191/26, and separate UKMTO 192/26 late 1 Nov, whose original document is not yet independently authenticated. Do not claim a confirmed attack or second witness from a relay.

All MSCIO material is treated as restricted for republication: only source URLs and operator-reviewed metadata are stored. Source-page availability is **not** proof of independent reporting origin, and distances/bearings without a documented exact location are **not** incident-site coordinates.

## Code change and regression

`apps/api/core/intel/official_maritime_bulletin.py`: source-locked MSCIO report ID ↔ URL mapping for the two verified *unnamed* reports, rejecting mismatched IDs/paths, query/fragment variants, or injected vessel name/IMO/MMSI. In particular, the secondary Reuters identification LOUISE 1 must not be smuggled into MSCIO:159/26 as if it were in the primary document. This guard applies even to direct adapter callers, not just manifest ingestion.

New files: `docs/research/maritime-attack-mscio-159-2026-11-02.json`, `docs/research/maritime-attack-mscio-162-2026-11-02.json`, `tests/test_maritime_attack_msio_159_162_manifest.py`. Test covers approximate event clock with no fabricated uncertainty bound, no exact coordinates, no primary-source ship identifiers, restricted rights, false independence/publication, source ID/URL mismatch, query/fragment contamination, and distinct event identities. Both candidates remain **staging-only** and **not publishable**.

Tested with existing Python virtual environment against a disposable clone, not production checkout. Python 3.8 syntax compilation and Ruff passed. Targeted tests **44 passed / 54 subtests**; full attack+official-bulletin suite on the final code **511 passed / 10 skipped / 378 subtests**. GitHub Actions CI on the new commit still requires a separate check before merge.

## Oracle PostgreSQL: verified read-only

Connected with `default_transaction_read_only=on`, `statement_timeout=6000`, confirmed `SHOW transaction_read_only = on`, rolled back. At 2026-11-02 **23:18:56 UTC**, rolling 72h starts **2026-10-30 23:18:56 UTC**.

| Relation and timestamp | Previous (~22:22 UTC) | Current |
| --- | ---: | ---: |
| `intel_events.timestamp_utc` | 10,630 | **10,623** |
| `vessel_tracks.ts` | 818,600 | **819,941** |
| `alert_events.timestamp_utc` | 0 | **0** |
| `anomaly_events.timestamp_utc` | 0 | **0** |
| `humanitarian_incidents.last_update_at` | 12 | **12** |
| `forensic_events.timestamp_utc` | 10 | **10** |
| `source_observations.observed_at` | 50,691 | **timeout 6s** |

These are moving-window counts, not net new inserts. The `source_observations` 72h query timed out and was **not** retried with a heavier query.

Additional read-only queries: `SELECT count(*) FROM source_observations WHERE observation_type='official_maritime_bulletin'` → **0**; October `maritime_episodes` with `episode_family IN ('attack','piracy','explosion','sinking')` → **0**; `pg_database WHERE datname LIKE '%_staging'` → **no database**. Therefore canonical bulletin ingestion and real PostgreSQL staging persistence remain unverified/unavailable.

**CONTSHIP JET** regression: `vessel_tracks WHERE mmsi='636019532' AND ts >= '2026-10-28' AND ts < '2026-10-29'` → **9** rows. At **09:59:22.678080** SOG **10.2 kn**, at **10:34:46.436674** SOG **0.6 kn**. Official Bulgarian MOD https://www.mod.bg/news9664 reports attack at **10:00 UTC** (12:00 local). AIS slowdown is temporal context, **not** an independent attack witness; no attribution of attacker and no invented attack point.

## LIVE/PLAY read-only

Public API https://api.seacommons.org/api/v1/ :

- `play/counts`: **3,589 total**, 132 humanitarian, 3,457 maritime; generated 2026-11-02 23:18:21 UTC. Previous count 3,588.
- Eight HTTP 200 pages from `play/incidents?limit=500&offset=...`: **3,589 rows, 3,583 unique IDs, six duplicates**; no attack/piracy/explosion/sinking classification in inspected incident-type fields. Offset pagination still does not guarantee a consistent snapshot.
- `live/signals?mode=maritime&days=3&limit=500`: **13 features** (10 AIS anomaly, 3 vessel incident), previous 14; no explicit attack classification.
- `live/pipeline`: AIS, first-party, public feeds, radio **live**; partner **degraded**. Radio DSC accepted **66** (previous 65); NAVTEX accepted **0**.

## HTTP reachability from VM, one-off, 6s timeout

`BG_TRANSPORT` HTTP 200 **57 ms**, VTMIS 200 **113 ms**, IMO 200 **131 ms**. MSCIO 159/162/164 returned **403** (152/104/105 ms) from VM despite their original pages being accessible through the web research path; do not claim successful VM ingest. UKMTO 403 **44 ms**, MARAD 403 **27 ms**, NATO Shipping Centre 403 **59 ms**, ONI 403 **27 ms**. Bulgarian MOD connection error. GDELT DOC API read timeout. These are HTTP response timings, **not** publication-to-ingestion latencies. No access restriction was bypassed.

Rights: UKMTO https://www.ukmto.org/terms-and-conditions (OGL terms and attribution conditions); MSCIO https://www.mscio.eu/terms-of-service/ (restricted redistribution; use metadata + links only). No automated source poller created.

## Remaining blockers and next step

Dedicated PostgreSQL `*_staging` and restricted append-only role are not provisioned; no INSERT/rollback/replay certification on a real staging database. Official canonical bulletin count remains zero. UKMTO/MSCIO relay independence unresolved, and PLAY pagination is non-snapshot. Next: provision separate staging only with explicit authorization, then test append-only lifecycle and review persistence; authenticate UKMTO 187-26 primary warning and separate Reuters ship identity lineage before any entity-resolution promotion. **Production remains untouched.**
