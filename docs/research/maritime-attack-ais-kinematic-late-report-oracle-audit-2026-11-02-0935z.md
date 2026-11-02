# SeaCommons maritime attack correlation — AIS integrity and late-report review

Audit window: 2026-11-02 09:26–09:36 UTC. Branch: `feature/maritime-attack-correlation-20261030`. Baseline: `b87a29c0`. **No production deployment, no production database writes, no VM cron/timer/persistent loop, no historical deletion or incident promotion.**

## Staging-only changes

1. `apps/api/core/intel/maritime_attack_staging_ais_context.py`: reject AIS fixes whose observation timestamp is more than five minutes after their purported receipt. An impossible reception chronology is not a vessel-motion observation. Check the maximum implied ground speed between adjacent AIS fixes (70 kn conservative sanity ceiling); when implausible, mark `ais_kinematic_conflict_signal=true` and suppress `sudden_stop_signal`. Keep the track as review context, not attack evidence. Never derive attack coordinates from AIS.
2. `tests/test_maritime_attack_staging_ais_context.py`: regression for a teleporting track, impossible receipt chronology, and small tolerated receipt skew. CONTSHIP JET's original plausible fixes remain a contextual slowdown and a 35.396-minute AIS sampling gap, **not** a second attack witness.
3. `docs/research/maritime-attack-mscio-163-2026-11-02.json`: metadata-only staging record for **MSCIO 163/26** (https://mscio.eu/alerts/199). The alert was published 30 October, but says only that an unidentified crude tanker was reportedly struck on **28 October** in the Strait of Hormuz. It gives no reliable event clock, IMO or MMSI. `event_date=2026-10-28` is deliberately day-only; rights `restricted_republication`; independent origin unverified; no automatic publication.
4. `tests/test_maritime_attack_staging_manifest.py`: regression that MSCIO 163/26 cannot acquire the name or IMO of another ship through downstream extraction.

## Read-only Oracle PostgreSQL audit

Connected through the existing application `DATABASE_URL`, without printing credentials. All SQL used `default_transaction_read_only=on`, `SET TRANSACTION READ ONLY`, a 5–7 second statement timeout and explicit rollback.

At **09:26:50 UTC** (72-hour cutoff **30 Oct 09:26:50 UTC**):

| Relation | Rows in moving 72h window | Prior 08:31 UTC |
| --- | ---: | ---: |
| `intel_events` | 10,241 | 10,169 |
| `vessel_tracks` | 805,025 | 804,220 |
| `alert_events` | 0 | 0 |
| `anomaly_events` | 0 | 0 |
| `humanitarian_incidents` updated | 21 | 21 |
| `forensic_events` | 11 | 11 |

These are **moving-window counts**, not a measured ingest rate. Exact `source_observations.observation_type='official_maritime_bulletin'` since 1 October: **0**. `maritime_episodes` in attack/piracy/explosion/sinking families: **0**.

A deliberately broad source-name regex returned 12 apparent official matches, but **all 12 were radio_receiver:thessaloniki_elektron_kiwisdr** observations; this is a substring false positive. The exact observation-type query returns zero. A title-only maritime-attack search in October returned no relevant vessel attacks, only unrelated Ukraine humanitarian posts.

**CONTSHIP JET**, MMSI `636019532`, 28 Oct: nine AIS fixes on the day; five between 09:45 and 11:10 UTC. Speed 10.2 kn at 09:59:22 and 0.6 kn at 10:34:46; the 35.396-minute gap is not proof of attack. Additional positions near 19:29–19:32 UTC are close to the later hazard position, but cannot reconstruct the path or attack site. Bulgarian MOD (https://www.mod.bg/news9664) documents the 10:00 UTC attack; VTMIS NAVWARN 768/26 (https://www.vtmis.bg/wx/wx_eng.htm) documents sinking at 20:30 UTC, IMO `9348625`. Do not count the sinking notice as independent attack corroboration.

**LOUISE 1** proposed crosswalk: IMO `9290323`, MMSI `352003797`, independently listed by Ukraine's government vessel registry (https://war-sanctions.gur.gov.ua/en/transport/ships/780) and VesselFinder (https://www.vesselfinder.com/vessels/details/9290323). Reuters 30 Oct (https://www.reuters.com/world/tanker-strait-hormuz-hit-by-limpet-mines-security-sources-say-2026-10-30/) attributes the name to three maritime-security sources for the **29 Oct 22:12 UTC** tanker attack reported by UKMTO/MSCIO 159/26. The issuing bulletins do not name the vessel. Identity-to-incident linkage remains **proposed, not independently certified**. Oracle has **zero AIS fixes** for MMSI `352003797` on 29 and 30 October; no invented AIS gap, track or speed change.

## LIVE / PLAY

Read-only public endpoints on `https://api.seacommons.org`:
- `/api/v1/play/counts`: 3,578 total (3,449 maritime, 129 humanitarian); snapshot generated 08:31:10 UTC.
- Bounded eight-page `/api/v1/play/incidents?limit=500&offset=...` scan: 3,579 rows, 3,573 distinct incident IDs, six repeated IDs; **zero attack/piracy categories** among returned rows. This is not a consistent database snapshot; paging duplicates remain.
- `/api/v1/live/signals?limit=300&days=3&mode=all`: 15 features, zero attack/piracy categories.
- `/api/v1/live/pipeline`: AIS live; first-party live; public feeds live; partner inputs degraded; radio live. NAVTEX end-to-end reception not certified in this run.

## Official-source access and rights

One-off bounded HTTP GET from the Oracle VM, measured **response latency**, not source-publication-to-ingest latency:
BG MOD 200/403ms; VTMIS 200/187ms; MSCIO 200/407ms; UKMTO homepage 200/252ms (homepage success does not prove alert API access); IMO 200/197ms; MARAD 403/41ms; NATO Shipping Centre 403/48ms; ONI 403/1037ms; GDELT request timed out after ~4.1s. No bypass. MSCIO content redistribution remains restricted; UKMTO OGL use is subject to attribution and third-party rights. The Ukrainian registry and Reuters are used as navigational references, not redistributed data dumps. Source rights and actual collector latency require further per-source review.

## Publication gate and next work

Neither an AIS stop nor a syndicated news article can become an independent attack witness. No perpetrator attribution. `publication_allowed=false` for all new records. Next: complete a persistent **isolated** staging database/reviewer with immutable source receipts and verified lineage groups, then test a gated PLAY-to-incident preview. Do not write to Oracle or deploy production without explicit approval.
