# SeaCommons — MSCIO 165/26 + UKMTO 192-26 cross-publisher lineage and read-only audit

Checked **2026-11-03 00:22–00:29 UTC** (Africa/Tunis 01:22–01:29). Branch `feature/maritime-attack-correlation-20261030`. Previous reported head: `2bea354e`. This is **staging-only code and metadata**: no Oracle database writes, production deploy, cron, timer, VM scheduler, historical record rewrite, or incident promotion.

## Newly authenticated original warning (last 72h)

**UKMTO:192-26**, original PDF https://www.ukmto.org/-/media/ukmto/products/20261102-ukmto_warning-192-26.pdf (document dated 2 Nov 2026; event **1 Nov 2026 23:47 UTC**; source listed as **Master**). Reports an *unnamed tanker* heading southeast, struck by **two unknown projectiles on the port side**, **72 NM east of Ras Al Khafji, Saudi Arabia**. All crew accounted for; no reported environmental impact. The original PDF was readable via the public web source; from the VM, one HTTP check returned **200 (119 ms)**, a later attempt to retrieve the PDF bytes returned **403**. Therefore the **original PDF SHA256 is not claimed or fabricated**.

**MSCIO:165/26**, original alert https://mscio.eu/alerts/201 (displayed publication **2 Nov 2026 11:45**, timezone not explicit; manifest retains day-only date). Reports **the same nominal event time, direction, distance, tanker type, two projectiles, port-side damage, crew safety**. This strongly suggests a shared upstream account or relay, **not two independent eyewitnesses**. The original MSCIO page returned **HTTP 200, 339 ms** from VM in this check. MSCIO and UKMTO report identities remain distinct, but the staging lineage review groups them as **one suspected origin** with **zero independently verified witnesses** and **publication_allowed=false**. No vessel name, IMO, MMSI, attack coordinates or attacker attribution inferred.

Both records have an event timestamp of 2026-11-01T23:47:00Z. MSCIO explicitly says approximately and is marked approximate **without invented numeric uncertainty**; UKMTO prints 2347UTC without an approximation qualifier. Both have **publication_date=2026-11-02**, not an invented publication instant or reception timestamp.

## Code and metadata changes

- `apps/api/core/intel/official_maritime_bulletin.py`: exact primary-source ID↔URL guards for **MSCIO 165/26** and **UKMTO 192-26**. Direct adapter calls reject swapped IDs, changed source paths, query/fragment variants, and injected vessel names/IMO/MMSI. Extends earlier MSCIO 159/162 source locks.
- `apps/api/core/intel/maritime_attack_staging_lineage.py`: explicit *manual* link basis `matching_event_details_unverified_origin`; requires both UTC clocks within **5 minutes**, different source hosts and a supporting original URL equal to one of the candidate source URLs. This is a **suspected shared-origin grouping**, never automated witness certification or permission to publish. Other geospatial and vessel-identity contradiction checks still apply.
- `docs/research/maritime-attack-mscio-165-2026-11-03.json` and `docs/research/maritime-attack-ukmto-192-2026-11-03.json`: source-checked metadata-only manifests, no attack point.
- `tests/test_maritime_attack_mscio165_ukmto192.py`: original source IDs, rights, date precision, lack of identity/geometry, false independence, strict matching clocks, incorrect source URLs, swapped report IDs, and conflicting IMO regression tests.

**Tests:** isolated checkout of this branch, not the dirty production worktree. Full attack + official bulletin test set: **518 passed, 10 skipped, 391 subtests passed**; Ruff **all checks passed**, `git diff --check` and Python compilation passed. Targeted set: **44 passed, 75 subtests**. No new GitHub Actions workflow run/status check was returned for this commit; do not call CI green.

## Oracle PostgreSQL read-only audit

Connection from authorized application configuration with `default_transaction_read_only=on`, `statement_timeout=6000`; `SHOW transaction_read_only` returned **on**. SQL read-only with rollback. Rolling 72h cutoff: **2026-10-31 00:24:28 UTC**. SQL for each relation: `SELECT count(*) FROM <table> WHERE <time_column> >= :cutoff` (UTC ISO text for varchar timestamp fields; naive UTC datetime for `vessel_tracks.ts`). Table/time field and counts:

| Relation | Previous (2026-11-02 23:18 UTC) | This run |
| --- | ---: | ---: |
| `intel_events.timestamp_utc` | 10,623 | **10,643** |
| `vessel_tracks.ts` | 819,941 | **821,351** |
| `alert_events.timestamp_utc` | 0 | **0** |
| `anomaly_events.timestamp_utc` | 0 | **0** |
| `humanitarian_incidents.last_update_at` | 12 | **12** |
| `forensic_events.timestamp_utc` | 10 | **10** |

Rolling-window differences are **not** net inserts. `source_observations WHERE observation_type='official_maritime_bulletin'` = **0**; October `maritime_episodes` with `episode_family IN ('attack','piracy','explosion','sinking')` = **0**. Available databases `postgres`, `seacommons`, `template1`; no `attack_review_staging` schema. No separate staging DB certified.

**CONTSHIP JET** regression: `SELECT ts,sog FROM vessel_tracks WHERE mmsi='636019532' AND ts >= '2026-10-28' AND ts < '2026-10-29' ORDER BY ts LIMIT 25` → **9 observations**. SOG **10.2 knots** at 09:59:22.678080 UTC; **0.6 knots** at 10:34:46.436674 UTC. Bulgarian Ministry of Defence https://www.mod.bg/news9664 reports attack at **12:00 local / 10:00 UTC** on 28 Oct and rescue. The AIS slowdown is **context, not independent evidence**. No attacker attribution or invented exact impact coordinates.

## Public LIVE/PLAY read-only

- `GET /api/v1/play/counts`: **3,589** total (132 humanitarian, 3,457 maritime), response generated 2026-11-03 00:24:37 UTC.
- Eight `GET /api/v1/play/incidents?limit=500&offset=...` calls all **HTTP 200**: **3,589 rows**, **3,583 unique IDs**, **six duplicate IDs**; **zero attack/piracy/explosion/sinking incident-type matches** in the inspected fields. Non-snapshot pagination persists.
- `GET /api/v1/live/signals?mode=maritime&days=3&limit=500`: **13 features**: 7 AIS gaps, 3 navigation safety, 2 position integrity, 1 dark activity. No explicit attack classification.
- `GET /api/v1/live/pipeline`: AIS, first-party, public feed live; partner **degraded**, radio **degraded**. Radio DSC accepted **68**; NAVTEX accepted **0**. No new VM scheduling or feed workers introduced.

## Official-source availability and rights

One-off HTTP GET from VM, with timeout 6s, no bypass: MSCIO165 **200/339ms**, MSCIO164 **200/388ms**, UKMTO192 PDF **200/119ms** initially but subsequent **403**; Bulgarian MOD **connect timeout ~6.1s**, Bulgarian Transport homepage **301/321ms**, VTMIS **200/210ms**, IMO **200/153ms**, MARAD **403/52ms**, NATO Shipping Centre **403/70ms**, ONI **403/612ms**, GDELT DOC API **read timeout ~6.1s**. These are **HTTP response times, not event-to-ingestion latencies**. Rights: UKMTO https://www.ukmto.org/terms-and-conditions (Open Government Licence with conditions); MSCIO https://www.mscio.eu/terms-of-service/ (restricts redistribution; keep only minimal metadata and links).

## Remaining blockers / next action

1. **No separate authorized PostgreSQL staging database or least-privilege append-only role**; no real INSERT/rollback/idempotency test or authenticated review promotion.
2. **Canonical official bulletin count remains zero** and PLAY still has non-snapshot pagination. Code is intentionally not wired into production ingestion.
3. **Source independence unresolved** for UKMTO192/MSCIO165 (treat as one suspected upstream report). No attacker attribution or incident promotion.
4. Need review of UKMTO source chain, exact permissions for original PDF redistribution, and independent eyewitness/original evidence before any promotion. The October Black Sea candidates remain under the same review gate.

No production deployment, database write, data deletion, historical rewrite, new VM cron/timer/loop, or incident promotion.
