# Maritime attack correlation — chronology guard, AZINI update, Oracle audit

Checked: **2026-11-02 21:20–21:24 UTC**. Scope: branch-only implementation, isolated tests, read-only production queries and public endpoint/source checks. No production deploy, no production write, no new VM cron/timer/loop.

## Change against previous run

Previous branch head: `de54c052`. New functional commits: `24161b93` (direct bulletin adapter), `0a7cc2c7` (lineage chronology), `22ae1b28` and `e059baf5` (regressions), `63ea727f` (Ruff import ordering). A publication date more than one calendar day before a reported event is now rejected, including when the direct official-bulletin adapter is called without the manual manifest. A one-day offset remains allowed because publication dates may be publisher-local. Precise UTC event/publication clocks are compared using only source-declared numeric uncertainty. This closes a bypass where day-only dates could describe an event days after publication.

Tested from a disposable shallow clone, not the dirty operational checkout: `PYTHONPATH=apps/api python -m pytest -q tests/test_maritime_attack*.py tests/test_official_maritime_bulletin.py` — **488 passed, 344 subtests passed**. Ruff on four touched files: **all checks passed**. GitHub Actions run `41527856793` was **in progress** when checked; do not label this latest run green until it completes. The temporary clone was deleted.

## Oracle PostgreSQL: read-only audit

Connection used `default_transaction_read_only=on`, 6-second statement timeout, explicit `BEGIN TRANSACTION READ ONLY` and rollback. No DDL or mutation. The 72-hour cutoff was **2026-10-30 21:20:54 UTC**.

| Table | Time column | 72h rows |
|---|---|---:|
| `intel_events` | `timestamp_utc` (varchar ISO) | 10,632 |
| `vessel_tracks` | `ts` (timestamp) | 817,358 |
| `alert_events` | `timestamp_utc` | 0 |
| `anomaly_events` | `timestamp_utc` | 0 |
| `humanitarian_incidents` | `last_update_at` | 12 |
| `forensic_events` | `timestamp_utc` | 10 |
| `source_observations` | `observed_at` | 50,569 |

These are moving windows, not net ingestion counts. Previous comparable figures: `intel_events` 10,638, `vessel_tracks` 816,255, humanitarian 12, forensic 10. Note that `intel_events.timestamp_utc` is VARCHAR: the initial parameterized comparison against a native timestamp failed with a type error and aborted that transaction; the successful second audit used ISO-formatted string comparisons for textual clocks.

Canonical `source_observations` with `observation_type='official_maritime_bulletin'`: **0 total**. October `maritime_episodes` families: gap 2,069; spoofing 227; safety 66; rendezvous 31; identity integrity 3; port call 2. **No attack/piracy family present.** Two October `intel_events.title` keyword hits are unrelated to attacks on ships (posts about attacks on migrants and energy infrastructure). This demonstrates the need for news-to-incident contextual filtering.

Databases: `postgres`, `seacommons`. Dedicated `*_staging` DB: **not provisioned**; `attack_review_staging` schema absent. No staging INSERT/rollback/idempotency test on a real separate PostgreSQL instance can be certified yet.

### Regression — CONTSHIP JET

IMO 9348625 / MMSI 636019532; test event 2026-10-28 10:00 UTC. Read-only query on `vessel_tracks` returned **9** positions on 28 October. At 09:59:22 UTC SOG was **10.2 kn**; at 10:34:46 UTC **0.6 kn**. Bulgarian Ministry of Defence report `news9664` describes a 12:00 local strike and rescue, without printing IMO or MMSI: https://www.mod.bg/news9664 . The AIS slowdown is **context**, never independent attack proof; no attacker attribution or incident-site reconstruction from later AIS points.

## Public LIVE / PLAY audit

Public API: `https://api.seacommons.org/api/v1/`.

`play/counts`: **3,588** items, 132 humanitarian, 3,456 maritime. Eight `play/incidents?limit=500&offset=...` pages returned 3,588 rows, **3,582 distinct incident IDs**, **6 duplicate IDs**. Offset pagination is not a consistent snapshot; absence claims are limited to rows returned. No explicitly attack/piracy/sinking/explosion-classified row in the inspected fields.

`live/signals?mode=maritime&days=3&limit=500`: **12** features (10 `ais_anomaly`, 2 `vessel_incident`), no explicitly classified attack. `live/pipeline`: three sources `live`, two `degraded` (source names not resolved from the compact API response). Compared with the previous run: PLAY 3,585 -> 3,588; LIVE 13 -> 12. Counts are not stable snapshots.

## Candidate incident evidence and new source update

- **MSCIO 161/26 — AZINI**: source page https://mscio.eu/alerts/197 now includes **UPDATE02**, explicitly stating that anti-piracy forces liberated the Iranian fishing vessel and that the piracy incident is considered **closed**. The actual liberation timestamp is **not specified** in the visible update; do not backdate or assign a time. The later reported vessel coordinates are not the original hijacking site. This is a new **closure/status update**, not a new attack or independent corroboration.
- **MSCIO 164/26 / UKMTO 191/26**, 1 November ~15:09 UTC, Hormuz: probable shared VHF Mayday origin, **not** two independent witnesses. Ship identity unresolved. Source: https://mscio.eu/alerts/200 .
- **UKMTO 192/26**, 1 November 23:47 UTC, ~72 NM east of Ras Al Khafji: separate tanker strike, unidentified vessel; the secondary reporting is derived from the same UKMTO warning, not independent corroboration. Primary PDF not reliably downloadable from VM; do not claim an authenticated original-document hash.
- **CHELSEA-3** and **HS DIGNITY**, Black Sea, 13 October: distinct Bulgarian Transport Ministry incidents. BTA ministry-derived report: https://www.bta.bg/en/news/bulgaria/1223918-transport-ministry-provides-details-on-two-ships-attacked-in-black-sea-confirms . HS DIGNITY AIS disappearance is a signal, not independent attack proof.
- **MSCIO 148/26**, 16 October ~19:22 UTC, Gulf: unnamed tanker reportedly struck by RPG; source https://mscio.eu/alerts/184 . No invented IMO/MMSI or exact position.

No candidate promoted to a canonical/public incident. Two independent **original** witness origins are not certified for any new promotion.

## HTTP reachability from authorized VM

One-shot `curl -L --max-time 6` checks; times are HTTP response times, **not event-to-ingestion latency**.

| Source | HTTP | Time |
|---|---:|---:|
| Bulgarian Defence `mod.bg/news9664` | 200 | 424 ms |
| Bulgarian Transport homepage | 200 | 423 ms |
| VTMIS NAVWARN | 200 | 176 ms |
| MSCIO 164/26 | 200 | 309 ms |
| UKMTO homepage | 403 | 56 ms |
| MARAD | 403 | 32 ms |
| NATO Shipping Centre | 403 | 59 ms |
| ONI | 403 | 2,047 ms |
| IMO | 200 | 156 ms |
| GDELT DOC API | timeout | 6,003 ms |

Reuse: UKMTO states Open Government Licence with conditions (https://www.ukmto.org/terms-and-conditions). MSCIO prohibits redistribution/publication outside its permitted uses (https://www.mscio.eu/terms-of-service/): keep its facts as restricted source metadata and link, do not mirror full notices. Bulgarian MOD webpage explicitly permits copying with source attribution. Other licences not certified in this run. HTTP 403 and timeout are **not** evidence that the upstream service is globally unavailable; do not bypass access controls.

## Remaining gates

1. Provision a **separate authorized PostgreSQL staging database** (not a schema inside production) with append-only role; run actual INSERT, rollback, replay and corruption tests there.
2. Build authenticated reviewer decisions and an immutable provenance trail for PLAY -> incident, requiring two verified independent original witness origins; retain non-humanitarian attack category/colour.
3. Acquire original official documents where permitted, preserving event/publication/receipt clocks, source links, hashes and rights; never treat AIS gaps or secondary news copies as proof.
4. Fix PLAY snapshot-consistent pagination and source acquisition before any production deployment.

**Safety boundary:** production unchanged, no Oracle writes, no deletion, no historical overwrite, no incident promotion, no new VM scheduling.
