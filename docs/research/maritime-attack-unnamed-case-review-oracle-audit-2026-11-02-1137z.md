# SeaCommons — Unidentified maritime attack review and Oracle audit

Audit: **2026-11-02 11:33–11:39 UTC**. Previous staging report: `d3fc3c68`. Functional commit: `8b4e15a0`. Branch: `feature/maritime-attack-correlation-20261030`.

## Staging implementation

`apps/api/core/intel/maritime_attack_staging_case_review.py` now accepts a single, **unidentified-vessel** attack candidate without inventing an IMO, MMSI, vessel name, coordinates or an exact event time. The source evidence ledger, URL, original report ID, event precision, publication/receipt clocks, reuse rights and digest remain visible. When a bulletin only reports a day, `attack_at_utc` remains `null`, with the original `attack_event_date` and `attack_time_precision='day'`. For an approximate source clock, `attack_time_precision='approximate'` is retained. A mismatch between event date and precise source clock is rejected.

Unidentified cases **cannot** link foreign follow-ups or AIS. Day-only cases cannot run the minute-resolution temporal correlator. The review continues to return `independent_origins_verified=0`, `publication_allowed=false` and `staging_only=true`; no automated PLAY promotion.

New regression tests cover MSCIO 164/26 (approximate time, unknown hull), MSCIO 163/26 (day-only, unknown hull), fabricated event dates, falsified precision, and attempts to attach unrelated wreck/AIS data.

CI: https://github.com/suezcanalxyz/seacommons/actions/runs/41438339282 — **success**. 412 correlation tests, 23 official bulletin tests, 11 isolated PostgreSQL tests, 3 SQLite tests = **449 Python tests**; 5 JavaScript tests and frontend build passed. Local targeted suite: 30 tests passed with 35 subtests; broader local suite before the final precision guard: 438 passed, 10 skipped (no isolated PostgreSQL fixture).

## Fresh candidate/source check

- **MSCIO:164/26** — https://mscio.eu/alerts/200 — 1 Nov 2026 approximately 15:09 UTC, Strait of Hormuz; a merchant master relayed a VHF Channel 16 Mayday concerning another vessel reportedly struck by an unknown projectile. Hull, IMO/MMSI, precise coordinates and crew status unavailable. One reporting lineage; not independently corroborated.
- **UKMTO:191/26** — UKMTO's official public homepage https://www.ukmto.org/ lists an attack report describing a master relaying another vessel's VHF Channel 16 Mayday in the Strait of Hormuz. This is a **probable shared underlying Mayday with MSCIO 164/26**, not a second independent witness. Exact source-document lineage and hashes still require verification.
- **UKMTO:192/26** — UKMTO's official homepage lists a **separate** 2 Nov attack report: tanker struck by two unknown projectiles on the port side, 72 NM east of Ras Al Khafji, all crew accounted for. A secondary 2 Nov report https://www.iranintl.com/en/202611025952 places the event at 1 Nov 23:47 UTC. The official numbered PDF https://www.ukmto.org/-/media/ukmto/products/20261102-ukmto_warning-192-26.pdf?rev=c10444e50bd94bb7b822cb1220ca09c3 returned HTTP 403 from the VM, so the exact minute is **not independently certified from the PDF** and no canonical source manifest was created. Do not merge with 191/26 or MSCIO 164/26.
- **CONTSHIP JET** (IMO 9348625, proposed MMSI 636019532) — 28 Oct 10:00 UTC attack in Black Sea reported by Bulgarian MOD https://www.mod.bg/news9664; NAVWARN 768/26 https://www.vtmis.bg/wx/wx_eng.htm documents subsequent 20:30 UTC sinking, not a second attack witness.
- October retrospective continues to include **ABLE**, **ALFA WATAN**, **MSCIO 159/26**, **MSCIO 162/26** and other distinct candidates. No attacker attributed. This is not an exhaustive all-seas census.

## Oracle PostgreSQL: direct read-only audit

Existing authorized application `DATABASE_URL`, explicit `SET TRANSACTION READ ONLY`, 6-second statement timeout, rollback; no writes. Snapshot at **2026-11-02 11:36:46 UTC**, rolling cutoff **2026-10-30 11:36:46 UTC**.

| Relation | 72-hour count | Prior 10:26 UTC |
| --- | ---: | ---: |
| intel_events | 10,368 | 10,300 |
| vessel_tracks | 808,235 | 806,626 |
| alert_events | 0 | 0 |
| anomaly_events | 0 | 0 |
| humanitarian_incidents (`last_update_at`) | 12 | 12 |
| forensic_events | 11 | 11 |

These are rolling-window counts, not ingestion deltas. Exact October `source_observations.observation_type='official_maritime_bulletin'`: **0**. October `maritime_episodes` with attack/piracy/explosion/sinking family: **0**.

CONTSHIP JET AIS read-only regression (`mmsi='636019532'`, 28 Oct 09:45–11:10 UTC): 5 fixes. 09:59:22 UTC 10.2 kn; 10:34:46 UTC 0.6 kn. Every `received_at` equals `ts`; independent acquisition latency unavailable. AIS slowdown is contextual, not an attack witness. Proposed LOUISE 1 MMSI 352003797: **0 fixes** 29–30 Oct; do not infer an AIS gap from no coverage.

## LIVE / PLAY public read-only check

At 11:33 UTC, `/api/v1/play/counts` reports **3,579** total (3,450 maritime; 129 humanitarian). Eight bounded pages `/api/v1/play/incidents?limit=500&offset=...` returned 3,579 rows but **3,573 unique incident IDs**, six duplicates. Zero attack/piracy/sinking/explosion categories among returned rows; pagination is not snapshot-consistent and cannot certify exhaustive coverage.

`/api/v1/live/signals?limit=300&days=3&mode=all`: **10 features**, no attack-like category. `/api/v1/live/pipeline`: AIS, first-party, public feed and radio live; partner degraded.

## Source availability measured from VM

One-off HTTP response times (not publication-to-ingestion latency): Bulgarian MOD 200/760 ms; VTMIS 200/210 ms; MSCIO 164 200/339 ms; UKMTO homepage 200/384 ms; IMO homepage 200/199 ms; MARAD 403/34 ms; NATO Shipping Centre 403/62 ms; ONI 403/999 ms; GDELT **homepage** 200/271 ms. GDELT homepage success does not establish API availability or ingestion reliability. UKMTO's public material is subject to its Open Government Licence conditions; MSCIO material remains conservatively restricted for republication pending source-specific clearance. No access restrictions bypassed.

## Open blockers and next intervention

1. Production canonical store still lacks official maritime bulletin observations. Stage an isolated, durable PostgreSQL source-observation store and authenticated reviewer without writing Oracle production.
2. Obtain primary UKMTO 191/26 and 192/26 documents and origin lineage; treat MSCIO 164/26 and UKMTO 191/26 as probable **one** Mayday witness until verified otherwise.
3. Persist original-document hashes and independent receipt timestamps, then evaluate actual corroboration. Never promote on AIS slowdown, duplicate publications or a later wreck notice alone.
4. Resolve PLAY pagination snapshot consistency before claiming exhaustive coverage.

**No production deployment, no Oracle writes, no historical record edits, no deletion, no incident promotion and no new cron/timer/loop/scheduler on the VM.**
