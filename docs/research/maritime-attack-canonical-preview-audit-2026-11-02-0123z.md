# Maritime attack correlation — canonical staging preview and Oracle audit

**Audit UTC:** 2026-11-02 01:19–01:23. **Base:** `44fe1e2d`. **Branch:** `feature/maritime-attack-correlation-20261030`. **Scope:** branch-only code, read-only production queries, disposable PostgreSQL CI tests. No production deployment, data deletion, schema migration, incident promotion or VM scheduling.

## What changed

`apps/api/core/intel/maritime_attack_staging_preview.py` now converts an **exactly matched** set of persisted canonical `SourceObservation` metadata and reviewed manifest entries into bounded **staging-only** review previews. The preview requires source ID, source policy, service/lane, URL, raw-payload SHA-256, subject IDs and the entire original provenance to match the source-faithful bulletin; re-derives the expected envelope to reject forged matching pairs. It rejects duplicate, missing, extra, cross-domain and tampered rows. Canonical receipt timestamps are normalized to explicit UTC, with the naive-UTC exception limited to the canonical DB receipt field.

Every preview is `publication_allowed=false`, `independent_origins_verified=0`, `ais_as_attack_proof=false`, and `staging_only=true`. The output intentionally has **no** public `incident_type` or `visual_category` field: `proposed_incident_type` and `review_color` are review UI hints only. Colors come from the existing canonical palette: attack `#ff6b35`, piracy `#a78bfa`; humanitarian categories remain untouched. A source-rights classification is **not** permission to republish: `reuse_rights_not_verified` is always a blocker.

New regression tests: `tests/test_maritime_attack_staging_preview.py`; the disposable PostgreSQL canonical writer test `tests/test_official_maritime_bulletin_postgres.py` now proves that all six real bulletin metadata envelopes can be written in a rollback-only transaction and transformed into six previews without creating a public episode. CI path filters were updated to include the new preview module/tests.

## Candidate preview inventory (NOT production incidents)

| Original report | Canonical observation ID derived from manifest | Proposed type | Review status |
| --- | --- | --- | --- |
| BG_MOD:news9664 | `obs:f779260a02490a03e91e00d858917e62` | maritime_attack | candidate; source name only, no original IMO/MMSI, no exact publication clock |
| MSCIO:158/26 | `obs:6a7731c5c03475cec4707e3ac172d2d2` | maritime_attack | candidate; vessel identity unknown, approximate clock unbounded |
| MSCIO:159/26 | `obs:84c8c8646d7c90fb5b101ee6a6b96fd4` | maritime_attack | candidate; vessel identity unknown, approximate clock unbounded |
| MSCIO:160/26 | `obs:2d6467d4867a145b505fe38144345bed` | none | context_only: suspicious approach, **not an attack** |
| MSCIO:161/26 | `obs:ac174f9dd81da1d7bf816586f4688439` | piracy | candidate; different category from physical attack |
| MSCIO:162/26 | `obs:83448e8d1986cc297ed554feef52fab7` | maritime_attack | candidate; vessel identity unknown, approximate clock unbounded |

These are **deterministic IDs for a hypothetical isolated staging ingestion**, not assertions that the observations already exist in Oracle. Every report still requires an independent-origin review and operator authorization. No aggressor is attributed.

## Oracle read-only audit

Read-only connection via existing application DSN; `PGOPTIONS=default_transaction_read_only=on,statement_timeout=7000`. No writes. Database clock observed: **2026-11-02 01:19:34 UTC**.

Rolling 72-hour counts (these are table counts, **not attacks**):
`intel_events=9,781`; `vessel_tracks=799,988`; `alert_events=0`; `anomaly_events=0`; `humanitarian_incidents` updated `=21`; `forensic_events=11`. Compared with previous 9,745/799,583/0/0/21/11, the rolling windows have moved; differences are not ingest deltas.

No rows returned by the October/early-November search for `official_maritime_bulletin` or source names matching UKMTO, MSCIO, MARAD, NAVAREA, Bulgarian MOD, IMO, GDELT. No `maritime_episodes` families matching attack/sinking/piracy. The canonical ingestion remains **unwired in production**.

**CONTSHIP JET** (IMO 9348625, MMSI 636019532): AIS 2026-10-28 09:57:55 UTC 10.8 kn; 09:59:22 10.2 kn; 10:34:46 0.6 kn; 10:46:24 0.7 kn; 10:58:15 0.8 kn. In these rows `received_at=ts`, not a measurable ingest delay. Ministry report `https://www.mod.bg/news9664` gives 12:00 Bulgarian local time (10:00 UTC), three observed impacts and crew rescue, **without** printing IMO/MMSI. The AIS deceleration is contextual only. October `intel_events` contains older CONTSHIP JET AIS gap/sudden-stop anomalies (5, 16, 19, 26 Oct); these are **negative controls** and not attack evidence.

## Public LIVE/PLAY

At ~01:20 UTC, PLAY counts: **3,576 total** (3,447 maritime, 129 humanitarian); full 3,576-row public catalog scan found **0** attack family/type/category. LIVE signals for 3 days: **13** signals, **0** attacks. Radio state `live`, 53 DSC accepted, **0 NAVTEX accepted**; partner `degraded`. This does not establish end-to-end attack ingestion.

## Source reachability from Oracle VM

One bounded GET per endpoint, elapsed wall-clock HTTP time only (not publication-to-ingest latency): Bulgarian MOD **200/340 ms**; MSCIO 159 **200/344 ms**; MSCIO 162 **200/297 ms**; IMO **200/124 ms**; MARAD **403/24 ms**; UKMTO **403/55 ms**; NATO Shipping Centre **403/30 ms**; ONI **403/29 ms**; GDELT **TLS timeout after 8,121 ms**. No bypass, no bulk scraping. MARAD 2026-012 remains active for the Black Sea until 2027-03-22; it is regional context, not incident proof.

MSCIO 159/26: 2026-10-29 22:12 UTC, Strait of Hormuz, reported tanker explosives; `https://mscio.eu/alerts/195`. MSCIO 162/26: 2026-10-30 18:00 UTC, Arabian Gulf, unknown projectile and fire; `https://mscio.eu/alerts/198`. MSCIO 160/26: suspicious approach, no shots and no boarding; `https://mscio.eu/alerts/196`. All remain unpromoted. MSCIO metadata-only linking avoids reproducing restricted bulletin text.

## Tests and remaining gates

Latest CI must certify the full branch head; the earlier `c0cb77a6` run `41372099255` was green with 357 maritime tests, 23 bulletin tests, 3 SQLite, 8 isolated PostgreSQL, 5 JavaScript and successful frontend build. New UTC receipt test added after that run; final branch CI should be checked separately.

Next: connect the canonical writer and this preview to a **dedicated isolated staging database and authenticated operator review surface**. Do not attach it to production LIVE/PLAY until source lineage, rights, independent corroboration, entity crosswalk and approval gates are complete. No new cron, timer, loop or VM scheduler.
