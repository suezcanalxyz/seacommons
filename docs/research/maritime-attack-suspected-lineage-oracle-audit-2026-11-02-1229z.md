# SeaCommons — Suspected shared-origin graph, MSCIO 158 and read-only audit

Audit: **2026-11-02 12:28–12:34 UTC**. Previous report: `f61f7fa5` (11:33–11:39 UTC). Branch: `feature/maritime-attack-correlation-20261030`. **Staging only; no production deploy.**

## Concrete changes

- Added `apps/api/core/intel/maritime_attack_staging_lineage.py`: bounded, deterministic *suspected* shared-origin graph for attack/piracy bulletin previews. Accepts only explicit HTTPS-supported hypotheses, never infers witness independence from distinct publishers, and always returns `independent_origins_verified=0`, `publication_allowed=false`. Rejects different event days, event times >120 minutes apart, contradictory named hulls/IMO/MMSI, incompatible incident-site coordinates, invalid timestamps, duplicate observations and transitive merges hiding incompatible sources. Hash fingerprints a **derived review snapshot**, not the source document.
- Added `tests/test_maritime_attack_staging_lineage.py`: 15 regression tests including **MSCIO 164/26 ↔ UKMTO 191/26** as one *suspected* VHF Mayday lineage, while **UKMTO 192/26** is temporally distinct. The test uses synthetic metadata for UKMTO; **the primary UKMTO PDF was not authenticated**. No unverified source can promote a case.
- Added source-checked, metadata-only `docs/research/maritime-attack-mscio-158-2026-11-02.json` and `tests/test_maritime_attack_msio_158_manifest.py`. Original official notice: https://mscio.eu/alerts/194 — attack reported at **approximately 16:00 UTC on 29 October**, Strait of Hormuz; unnamed tanker reportedly hit by an unknown projectile. No invented IMO/MMSI/coordinates. Publication day **29 October**; exact publication clock absent from manifest. Reuse rights conservatively `restricted_republication`.
- Existing `maritime_attack_relay_lineage.py` and `maritime_attack_lineage_readonly.py` require reviewed/verified dependencies. The new module is a separate **pre-review hypothesis layer**, not a replacement for those verification gates.

**GitHub commits:** `130057f1` (staging graph), `5a2af6c0` (regressions), `62ec7655` (MSCIO 158 manifest), `9b90805e` (manifest test), `2db0119f` (ruff import formatting).

**Tests actually run on detached staging worktree:** `pytest tests/test_maritime_attack_*.py` — **428 passed, 226 subtests passed** (before formatting-only commit). After final formatting change, **16 focused tests passed, 7 subtests passed**, and `ruff check` passed. **No new GitHub Actions CI run is claimed.** Tests used the pre-existing Python venv and a disposable worktree, never the dirty production checkout.

## Oracle PostgreSQL — read-only audit

Connection: existing authorized `DATABASE_URL`, `default_transaction_read_only=on`, 7-second statement timeout, autocommit SELECT only; no DML or schema changes. Snapshot: **2026-11-02 12:28:57 UTC**; 72-hour cutoff **2026-10-30 12:28:57 UTC**.

| Relation / clock | Current 72h | Previous 11:36 UTC |
| --- | ---: | ---: |
| `intel_events.timestamp_utc` (ISO text) | 10,438 | 10,368 |
| `vessel_tracks.ts` | 809,433 | 808,235 |
| `alert_events.created_at` | 0 | 0 |
| `anomaly_events.created_at` | 0 | 0 |
| `humanitarian_incidents.last_update_at` (ISO text) | 11 | 12 |
| `forensic_events.created_at` | 13 | 11 |

These are moving-window counts, not ingestion deltas. `forensic_events` classes: **12 distress, 1 resolved**; no attack class. October `source_observations.observation_type='official_maritime_bulletin'`: **0**. October `maritime_episodes` families: gap 2,075; spoofing 228; safety 67; rendezvous 30; identity_integrity 3; port_call 2; **attack/piracy/sinking/explosion 0**.

Representative read-only queries:

```sql
SELECT count(*) FROM vessel_tracks
WHERE ts >= (now() AT TIME ZONE 'UTC') - interval '72 hours';

SELECT count(*) FROM source_observations
WHERE observation_type = 'official_maritime_bulletin'
  AND observed_at >= '2026-10-01' AND observed_at < '2026-11-01';

SELECT episode_family, count(*) FROM maritime_episodes
WHERE start_at >= '2026-10-01' AND start_at < '2026-11-01'
GROUP BY episode_family;
```

**CONTSHIP JET regression:** MMSI `636019532` between 28 Oct 09:45 and 11:10 UTC returned five AIS fixes. 09:59:22 at **10.2 kn**; 10:34:46 at **0.6 kn**. IMO `9348625` supported separately by NAVWARN 768/26 (later sinking), not retroactively inserted into the Bulgarian MOD attack document. AIS slowdown remains context, not attack proof. Proposed LOUISE 1 MMSI `352003797`: **zero fixes** 29–30 Oct; absence of coverage is not a verified AIS gap.

## LIVE/PLAY public read-only audit

At 12:29–12:33 UTC, `https://seacommons.org/api/v1/play/counts`: **3,579 total** (3,450 maritime; 129 humanitarian). Nine paginated reads returned **3,579 rows, 3,573 distinct IDs, six duplicates**, with nine different page generation timestamps. No attack/piracy/sinking/explosion type among returned rows; cannot claim exhaustive consistent snapshot.

`/api/v1/live/signals?limit=300&days=3&mode=all`: **10 signals** — seven `ais_gap`, one `navigation_safety`, one `dark_activity`, one `distress`; zero attack type. `/api/v1/live/pipeline`: AIS, first-party, public feed and radio live; partner degraded; radio DSC accepted 61, NAVTEX accepted 0.

## Source availability, rights, uncertainty

Single-request VM measurements (HTTP response time, **not** publication-to-ingestion latency):

| Source | HTTP / milliseconds |
| --- | --- |
| Bulgarian MOD | 200 / 395 |
| VTMIS | 200 / 169 |
| MSCIO 164/26 | 200 / 2,166 |
| UKMTO homepage | 200 / 184 |
| UKMTO 192/26 PDF | **200 / 52**, then **403** on content fetch; **original PDF NOT verified** |
| IMO | 200 / 152 |
| MARAD | 403 / 36 |
| NATO Shipping Centre | 403 / 37 |
| ONI | 403 / 33 |
| GDELT DOC API | read timeout / 8,134 |

UKMTO site content is published under Open Government Licence with conditions: https://www.ukmto.org/terms-and-conditions. MSCIO reuse conservatively restricted pending source-specific clearance. GDELT datasets are free/open but hosted APIs have rate limits: https://gdeltproject.org/data.html and https://blog.gdeltproject.org/ukraine-api-rate-limiting-web-ngrams-3-0/. No restrictions bypassed; no PDF hash invented from a 403 HTML response.

## Priority candidates and blockers

1. **MSCIO 164/26**, 1 Nov ~15:09 UTC, Hormuz, unknown struck vessel: https://mscio.eu/alerts/200. **UKMTO 191/26** likely same original VHF Channel 16 Mayday, not a second witness. Suspected link is *not* certified documentary lineage.
2. **UKMTO 192/26**, 1 Nov reportedly 23:47 UTC, 72 NM east of Ras Al Khafji, unnamed tanker; **separate** event. Minute precision still secondary-source only because primary PDF not successfully retrieved.
3. **MSCIO 158/26**, 29 Oct ~16:00 UTC, unnamed tanker, Hormuz: https://mscio.eu/alerts/194. Newly added staging metadata; not linked automatically to MSCIO 159/26 (~22:12 UTC) or another ship.
4. **CONTSHIP JET**, 28 Oct 10:00 UTC, Black Sea, IMO 9348625, proposed MMSI 636019532: Bulgarian MOD https://www.mod.bg/news9664; VTMIS https://www.vtmis.bg/wx/wx_eng.htm later sinking 20:30 UTC. Reuters independently verified some footage but underlying footage provenance and independent origin still require case review; no attacker attributed.

**Blockers:** canonical store has no official bulletins; no durable isolated PostgreSQL staging review surface; no authenticated UKMTO 191/192 PDF/hash; no independent source-receipt latency; PLAY pagination is not snapshot-consistent. Next: build a reviewed lineage-to-canonical staging adapter with explicit source hashes and authentication, then verify end-to-end against isolated PostgreSQL. Do not publish on suspected links or AIS anomalies.

**Safety:** no production deployment, no production database writes, no historical edits/deletions, no incident promotion, and no cron/timer/loop/scheduler created on Oracle.
