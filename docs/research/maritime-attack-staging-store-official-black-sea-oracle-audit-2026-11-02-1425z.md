# SeaCommons — Maritime attack correlation / staging snapshot adapter
Audit: **2026-11-02 14:24–14:40 UTC**. Branch: `feature/maritime-attack-correlation-20261030`. Previous documented head: `98161cba`, audit at 13:32 UTC. No production deployment.

## Implemented on branch (no staging DB writes yet)

- `apps/api/core/intel/maritime_attack_staging_store.py`: a PostgreSQL-only, **append-only** snapshot adapter. Revalidates the complete case JSON, its source-evidence ledger digest, the attack identity, the non-publishable status, the unverified witness status, and the attack/piracy visual color. Snapshot IDs and hashes are deterministic; changed evidence produces a new snapshot, never an UPDATE. The write boundary requires an explicitly named dedicated `*_staging` database, checks `current_database()`, transaction read-only status and a pre-provisioned table. The caller owns the transaction. It creates no engine/schema, does not commit, and never writes to canonical incidents.
- `docs/research/maritime-attack-staging-review-schema.sql`: manually applied DDL **only** for a separate staging database. It fails on any DB name not ending `_staging`, revokes PUBLIC privileges, and creates an isolated `attack_review_staging.review_snapshots` table. **Not executed** in this run. A dedicated staging database and least-privilege role still need provisioning.
- `tests/test_maritime_attack_staging_store.py`: deterministic/idempotent replay, tamper detection, fake witness rejection, production DB/SQLite rejection, read-only transaction rejection, and no UPDATE/DELETE/commit assertions.
- An actual CONTSHIP JET case review was converted into a valid, **unpublished** snapshot: `staging-case-review:obs:f779260a02490a03e91e00d858917e62`; snapshot ID `22a08645859871a12dee8e8c11896502bd4d31499614c225281c5685a5e1351f`; four ledger entries; zero verified independent origins. This was in-memory only, not inserted into a database.

### October retrospective: two separate official Bulgarian ministry cases

Direct original: https://www.mtc.government.bg/en/category/1/technical-information-vessels-affected-and-those-provided-assistance-maritime-areas-republic-bulgaria-over-past-24-hours (published **13 Oct 2026**, HTTP 200 from VM / 293 ms).

- `BG_TRANSPORT:20261013-chelsea-3`: CHELSEA-3, Malta flag, attack reported at **01:15** in the source, 17 NM east of Byala; 15 rescued. The page does **not** label 01:15 as UTC. Staging manifest therefore records **2026-10-13 day precision**, not an invented UTC timestamp, IMO/MMSI, or coordinates.
- `BG_TRANSPORT:20261013-hs-dignity`: HS Dignity, Guinea-Bissau flag, drone strike reported at **01:20** in the source, sinking 17 NM east of Shabla; five survivors assisted by AZOV CONCORD and SCANDI ASSERTER. A rescued sailor's report of sinking coincided with AIS loss; **AIS loss is context, not proof of attack**. Likewise day precision; no invented IMO/MMSI or exact coordinates.
- Separate manifests: `docs/research/maritime-attack-bg-transport-chelsea-3-2026-11-02.json` and `...-hs-dignity-2026-11-02.json`. They share one source page but have different report IDs and vessels. Regression rejects a proposed merge based on that shared document; no independent origins are inferred.

Additional reference: https://www.bta.bg/en/news/bulgaria/1223918-transport-ministry-provides-details-on-two-ships-attacked-in-black-sea-confirms (13 Oct). The BTA item is a relay of the ministry, **not a second independent originating witness**.

## Oracle PostgreSQL — read-only verification

Used existing authorized application DB credentials without displaying them. SQLAlchemy connections set `default_transaction_read_only=on`, `statement_timeout=7000`; SELECT only, explicit rollback. Rolling cutoff **2026-10-30 14:25 UTC**. Previous rolling cutoff **2026-10-30 13:32 UTC**; counts are **not** ingest deltas.

| Relation / timestamp field | Current 72h | Previous |
| --- | ---: | ---: |
| `intel_events.timestamp_utc` | 10,506 | 10,475 |
| `vessel_tracks.ts` | 810,835 | 810,426 |
| `alert_events.created_at` | 0 | 0 |
| `anomaly_events.created_at` | 0 | 0 |
| `humanitarian_incidents.last_update_at` | 11 | 11 |
| `forensic_events.created_at` | 13 | 13 |

`forensic_events.classification`: 12 `distress`, one `resolved`. All-time `source_observations.observation_type='official_maritime_bulletin'`: **0**. October observed-at and created-at counts for that type: **0**.

Correct `maritime_episodes` classification column is `episode_family` (not `episode_type`). For October **by `start_at`**: 2,075 `gap_episode`, 228 `spoofing_episode`, 66 `safety_episode`, 30 `rendezvous_episode`, 3 `identity_integrity_episode`, 2 `port_call_episode`, and **0 attack/piracy/sinking/explosion episode families**. Filtering by `created_at` yields different numbers and must not be conflated with the October event-time retrospective.

CONTSHIP JET regression: `SELECT ts,sog,lat,lon FROM vessel_tracks WHERE mmsi='636019532' AND ts BETWEEN '2026-10-28 09:45' AND '2026-10-28 11:10' ORDER BY ts` returned five fixes, including **09:59:22 / 10.2 kn** and **10:34:46 / 0.6 kn**. Bulgarian MOD https://www.mod.bg/news9664 reports the attack at 10:00 UTC; VTMIS https://www.vtmis.bg/wx/wx_eng.htm NAVWARN 768/26 documents a **separate** sinking at 20:30 UTC. IMO 9348625 appears in the NAVWARN; the MMSI crosswalk is still not an independently certified original-source identifier. No attacker attributed.

## LIVE / PLAY — read-only public endpoints

- `GET https://api.seacommons.org/api/v1/play/counts`: **3,580** (3,451 maritime; 129 humanitarian).
- `GET /api/v1/play/incidents?limit=500&offset=...`: eight pages, **3,580 returned rows, 3,574 unique incident IDs, six duplicates** across eight distinct page timestamps. No attack/piracy incident type among returned rows. Pagination is not a consistent snapshot.
- `GET /api/v1/live/signals?limit=300&days=3&mode=all`: **12** signals (9 AIS anomalies, 2 vessel incidents, 1 Twitter), no attack-classified signals.
- `GET /api/v1/live/pipeline`: AIS, first-party, public feed, radio live; partner degraded; DSC accepted **63**; NAVTEX accepted **0**. Public API revision `790c460e30c2`.

## Source accessibility and reuse (one-shot VM HTTP GET)

| Source | HTTP / elapsed |
| --- | --- |
| Bulgarian MOD | 200 / 660 ms |
| Bulgarian VTMIS | 200 / 117 ms |
| Bulgarian Transport, 13 Oct | 200 / 293 ms |
| MSCIO 164/26 | 403 / 143 ms |
| MSCIO 158/26 | 403 / 107 ms |
| UKMTO terms | 403 / 52 ms |
| IMO | 200 / 126 ms |
| MARAD | 403 / 34 ms |
| NATO Shipping Centre | 403 / 47 ms |
| ONI | 403 / 66 ms |
| GDELT DOC API | read timeout / ~6,168 ms |

HTTP timings are **not** publication-to-ingest latency. No 403 bypass attempted. UKMTO terms https://www.ukmto.org/terms-and-conditions say Open Government Licence with conditions; importantly UKMTO shares some submitted reports with MSCIO, so different publisher IDs are not sufficient evidence of independent witnesses. MSCIO https://mscio.eu/terms-of-service/ restricts redistribution. GDELT is free/open but API rate-limited: https://blog.gdeltproject.org/ukraine-api-rate-limiting-web-ngrams-3-0/. Bulgarian ministry reuse remains attribution-conditioned.

## Candidate queue and blockers

- `BG_MOD:news9664` / CONTSHIP JET — 28 Oct, Black Sea; direct MOD attack report plus separate wreck NAVWARN and AIS context; no second verified originating witness.
- `BG_TRANSPORT:20261013-chelsea-3` and `BG_TRANSPORT:20261013-hs-dignity` — **new source-checked official October candidates**; day-only UTC precision, no verified IMO/MMSI, separate vessel identities, no incident promotion.
- `MSCIO:164/26` / suspected `UKMTO:191/26` — 1 Nov ~15:09 UTC, Hormuz, unidentified ship, likely shared VHF Mayday; no double corroboration.
- `UKMTO:192/26` — 1 Nov ~23:47 UTC reported east of Ras Al Khafji; distinct event; original numbered PDF still not independently authenticated.
- `MSCIO:158/26`, `159/26`, `162/26` and other October cases remain review-only; LOUISE 1 crosswalk not a second attack witness.

## Tests and release boundary

On isolated temporary Git worktree at commit `6c025674`: **442 Python tests passed, 253 subtests passed**, Ruff passed on all newly modified Python files. A real CONTSHIP JET review successfully produced an in-memory snapshot. No PostgreSQL staging integration test was run because **no dedicated staging database has been provisioned**. No new GitHub Actions success is claimed.

Next: provision a separate `*_staging` PostgreSQL database and least-privilege INSERT/SELECT role; manually apply the guarded schema there; test transaction rollback, idempotent replay and tamper detection on real staging PostgreSQL. Then build an authenticated review surface. Only verified independent originating observations and explicit approval could later allow PLAY-to-incident promotion.

**No production deployment, Oracle writes, historic edits, deletion, promotion, new cron, timer, loop or VM scheduler.**
