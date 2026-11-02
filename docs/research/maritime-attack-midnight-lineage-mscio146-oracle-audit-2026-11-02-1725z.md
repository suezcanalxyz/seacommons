# SeaCommons attack-correlation staging — 2 November 2026, 17:25 UTC

Scope: manual, one-shot research and read-only Oracle PostgreSQL audit; staging branch only. No cron, timer, VM scheduler, production deployment, production DB write, historical mutation or incident promotion.

## Change since previous run

Previous staging head: `5446da1e`. Fixed a false-negative in `maritime_attack_staging_lineage._compatible`: two source notices for the same UTC event could not be linked across midnight because their UTC calendar dates differed. Both notices must still carry timezone-aware event clocks within 120 minutes; a day-only report retains the strict same-day requirement. Cross-midnight conflicting IMO or geographically incompatible incident sites continue to fail closed. All suspected links retain zero verified independent origins and `publication_allowed=false`.

Added five regression cases: near-midnight compatible clocks, distant clocks, day-only mismatch, conflicting IMO, conflicting geography. Added one metadata-only MSCIO source manifest and its validation regression.

## Newly verified October candidate

`MSCIO:146/26` — source https://mscio.eu/alerts/182; October 13, 2026, approximately 17:00 UTC, Strait of Hormuz. MSCIO published a time-late report October 14: an unnamed container vessel was reportedly hit by an unknown projectile during outbound transit, sustaining minor damage, with no reported casualties. Original page does not identify IMO, MMSI, vessel name, precise position or attacker. Publication is recorded only at day precision because the displayed webpage clock is not independently certified as UTC. Source checked 2026-11-02; metadata-only manifest `docs/research/maritime-attack-mscio-146-2026-11-02.json`, `restricted_republication`; no copied source text, original document hash, verified independent origin or automatic publication.

This is separate from October 13 Black Sea CHELSEA-3 and HS DIGNITY events (different sea and reported time). Existing last-72h priority MSCIO 164/26 / suspected UKMTO 191/26 remains one potentially shared VHF Mayday origin, not two independent attack witnesses. UKMTO 192/26 remains a distinct, incompletely authenticated episode. CONTSHIP JET IMO 9348625 / MMSI 636019532 is the fixed October 28 regression, not a newly discovered attack.

## Oracle PostgreSQL: authorized application connection, read-only

Used existing configured application DB connection, without displaying secrets. Connection-level `default_transaction_read_only=on`, explicit `BEGIN TRANSACTION READ ONLY`, local 6s statement timeout, SELECT-only SQL and `ROLLBACK`. `SHOW transaction_read_only` returned `on`.

Rolling 72h cutoff `2026-10-30T17:25:00Z` (not an ingest delta relative to previous moving window):

| Table / time column | Rows |
| --- | ---: |
| `intel_events.timestamp_utc` | 10,582 |
| `vessel_tracks.ts` | 813,414 |
| `alert_events.created_at` | 0 |
| `anomaly_events.created_at` | 0 |
| `humanitarian_incidents.last_update_at` | 9 |
| `forensic_events.created_at` | 8 |

`source_observations` all-time `observation_type='official_maritime_bulletin'`: **0**. October 2026 `maritime_episodes` `episode_family` among `attack,maritime_attack,piracy,explosion,sinking`: **0**. Therefore the official-source-to-canonical-store gap is unresolved.

CONTSHIP JET regression (MMSI `636019532`, 2026-10-28 09:45–11:10 UTC): five AIS fixes; 09:59:22 UTC / 10.2 kn and 10:34:46 UTC / 0.6 kn. Coordinates are AIS vessel fixes, not attack-site evidence. Bulgarian Defence Ministry https://www.mod.bg/news9664 documents the attack at 10:00 UTC; later NAVWARN 768/26 at https://www.vtmis.bg/wx/wx_eng.htm concerns sinking at 20:30 UTC, a separate event. No perpetrator assigned; no second independent attack witness inferred from AIS or wreck notice.

## Public LIVE/PLAY (one-shot read-only HTTP)

Eight PLAY requests `/api/v1/play/incidents?limit=500&offset=0,500,...,3500`: all HTTP 200, 3,583 returned rows, 3,577 unique incident IDs, six repeated IDs, zero attack/piracy/explosion/sinking labels in returned rows. Catalog counts endpoint gave 3,581 from a cached 15:25 UTC snapshot, while the paginated catalog at 17:24 UTC reported 3,583. This is not a consistent snapshot, and is not proof that no attack exists outside returned rows.

LIVE `/api/v1/live/signals?days=3&mode=all&limit=500`: 14 features, 12 AIS gaps and 2 navigation casualties, zero attack visual categories. Pipeline endpoint revision `790c460e30c2`; AIS, first-party and public feeds live, partner degraded.

## VM HTTP accessibility, one-shot checks (not ingest latency)

| Source | HTTP / elapsed |
| --- | --- |
| Bulgarian Defence Ministry | 200 / 353 ms |
| Bulgarian VTMIS | 200 / 104 ms |
| MSCIO 146/26 | 200 / 281 ms |
| MSCIO 164/26 | 200 / 244 ms |
| UKMTO | 403 / 47 ms |
| MARAD | 403 / 29 ms |
| NATO Shipping Centre | 403 / 17 ms |
| ONI | 403 / 27 ms |
| IMO | 200 / 129 ms |
| GDELT DOC API | connection error / 7.1 s |

Access and HTTP timing are not evidence of ingestion or publication-to-receipt latency. No access restriction was bypassed. Rights remain source-specific: MSCIO conservatively `restricted_republication`; UKMTO Open Government Licence subject to its terms; check individual documents before redistribution.

## Tests and release boundary

On an isolated temporary checkout of the staging branch, Python 3.12 with SQLAlchemy: `python -m unittest discover -s tests -p 'test_maritime_attack_*.py'` — **449 tests passed**. Ruff passed on modified Python files. This is not a real PostgreSQL staging integration test, nor a full GitHub Actions certification. No dedicated `*_staging` database was provisioned, schema applied or rows inserted.

Next: independent original-source review and authenticated operator approval design, followed by a dedicated, separately authorized PostgreSQL staging DB for rollback, replay and append-only tests. Production publication remains blocked.
