# SeaCommons master technical and intelligence audit — 2026-11-19

Status: repository audit, public-production observation and bounded implementation in an isolated worktree. No Oracle mutation, database migration, process restart or deployment was performed.

## 1. Scope, evidence and limitations

This audit inspected `origin/main` at `714df4c0`, PRs #543–#546, the FastAPI/web code, migrations, tests, public production APIs, Vercel project metadata and primary-source data documentation. The modified local main checkout was not changed. Work was performed on `audit/master-research-20261119` under `.tmp/worktrees/master-research-20261119`.

The Oracle host could not be reached through the historically configured SSH address and the current upstream hostname is redacted by the Vercel connector. Therefore this audit does **not** claim current Oracle disk, process, PostgreSQL plan, Redis memory, R2 connectivity, object inventory, systemd state or deployment checkout state. The historical “80% root / 9 GB free” figure remains unverified and must not be presented as current.

## 2. Current read-only production baseline

Observed between 17:55 and 18:19 UTC on 2026-11-19:

| Surface | Result | Measured response |
|---|---:|---:|
| `https://seacommons.org/` | HTTP 200 | 1.154 s |
| `https://live.seacommons.org/` | HTTP 200 | 0.441 s |
| `https://play.seacommons.org/` | HTTP 200 | 0.772 s |
| API `/health` | HTTP 200, `status=ok` | 0.782 s |
| API `/ready` | HTTP 200, PostgreSQL `ok` | 0.947 s |
| LIVE signals, one row | HTTP 200 | 1.307 s |
| PLAY incidents, one row | HTTP 200 | 0.437 s |
| `/api/v1/ops/summary` | HTTP 200, 3.5 KB | 0.612 s |
| `/api/v1/ops/overall` | HTTP 200, 2.0 KB | 2.041 s |
| `/api/v1/ops/data-status` | HTTP 200, 7.0 KB | 1.169 s |

These are single client-side samples, not percentile latency or capacity measurements. A release gate needs repeated p50/p95/p99 measurements and database query plans.

### Runtime facts exposed by the current API

- Production reports backend revision `790c460e30c2`; `origin/main` was `714df4c0`. The deployed backend therefore does not represent current main and does not include the observable #543 dossier fields.
- FastAPI reports operational profile, PostgreSQL, configured Redis, durable database queue, configured CMEMS and connected Mediterranean AISStream.
- In the last 24 h: 21,222 raw observations, 1,236 parsed events, 1,081 derived cues, 84 maritime episodes, 15 hypotheses, 4 multi-source-corroborated episodes, 3 review-ready items, 249,421 AIS fixes, 2,228 radio bursts, 121 radio events, 156 satellite observations and 12 active source names.
- The retained IntelEvent store reported 436,674 rows, of which 435,528 were positioned. This is retained application data, not a lifetime immutable archive.
- `available_ram_mb=7330` was reported by the app. This is not disk capacity and does not validate the historical filesystem statement.
- The operations summary reported nine radio receivers configured/runnable, five started and one failed at 18:17 UTC. A mesh request about one minute later reported only two connected receivers. This volatile divergence needs a single timestamped runtime snapshot and a definition for “started” versus “connected”; neither number should be advertised as a stable receiver count.
- Decoder state at the mesh sample: 2 decoders, about 2.5 million process-lifetime frames, 1 accepted DSC record, 0 accepted NAVTEX, 259 dropped frames, 24 invalid messages and 2,036 continuity resets. Process-lifetime counters are not a time-bounded service-level measure.
- IOM Missing Migrants was offline with 28 consecutive HTTP 404 failures. Sea-Watch RSS was unavailable with 98 consecutive 404 failures. The NGO AIS feed was degraded with a 60-second timeout. These are current silent-coverage risks even though aggregate health remained operational.

### Security and exposure drift

An unauthenticated request to the production vessel dossier endpoint returned complete track history for XT EXPLORATION and MINSTREL. Current `origin/main` calls `require_roles()` for that route. This is a deployment/configuration drift or older-code exposure and should be treated as P0 until the intended access policy is verified.

The public receiver mesh returned unreviewed discovery rows whose `station_label` was the raw receiver URL/IP. That conflicts with the code’s own privacy test intent and exposes receiver endpoints that have no public identifier, permission or geolocation. The isolated fix now omits unreviewed rows from the public row list while retaining aggregate catalogue counts.

## 3. Deployment and PR reconciliation

| PR | Merged commit | Intended change | Audit result |
|---|---|---|---|
| #543 | `1c3337a3` | AIS discontinuity evidence and XT EXPLORATION regression | Merged, but production revision does not expose `track_discontinuities`. The implementation also rejected production-style naive PostgreSQL timestamps, so valid fix count would be zero until UTC serialization is fixed. |
| #544 | `5121f375` | Larger receiver pool and show active geolocated receivers | Behavioural change is intentional; one frontend test still asserted the old regional exclusion. |
| #545 | `5ed3bdb0` | Remove hard cap on channel replicas | Merged; config test still asserted the old exact default. |
| #546 | `714df4c0` | Use all authorized physically distinct candidates | Merged; same stale tests and repository gate remained red. |

The merge-head Full CI run had four independent failures:

1. `tests/test_config.py` expected `REMOTE_RADIO_CHANNEL_REPLICAS == 3`, actual 6.
2. `radioMap.test.js` expected inland active receivers to be hidden, contrary to #544–#546.
3. `external_navtex.py` introduced direct `urlopen`, failing the governed outbound-HTTP inventory.
4. Full JS lint failed because the repository currently has 95 warnings and enforces `--max-warnings 0`. This is broader debt and was not suppressed.

The isolated branch fixes the first three without weakening gates. The lint debt remains an explicit release gate.

## 4. System dependency graph

```text
AISStream / official feeds / NGO reports / radio receivers / satellite catalogues
  -> collectors and protocol clients
  -> queue, durable SQLite AIS spool, scheduler and radio PCM queues
  -> SourceObservation / VesselTrack / RadioBurst / SatelliteObservation
  -> schema and source-policy validation
  -> AIS registry + entity graph + identity screening
  -> geospatial reference, coverage, track segmentation and drift forcing
  -> lineage, correlation decisions, episodes and hypotheses
  -> PostgreSQL hot store + optional private object references + Redis caches
  -> FastAPI operator/public projections
  -> LIVE / PLAY / FUTURES and Vercel proxy
  -> review, publication and evidence dossier
```

### Stage audit

| Stage / owner | Input → output and current frequency | Failure and silent-failure modes | Tests / observability / resource risks | Principal gap and recommended change |
|---|---|---|---|---|
| Source acquisition — `core.vessels.aisstream`, `core.intel.news_monitor`, `core.mda.navarea3`, radio providers, satellite resolver | AIS continuous; incident watch 5 m; NAVAREA 30 m; news 30 m; IOM 1 h; receiver discovery 6 h; satellite enrichment 30 m | Provider timeout/404, unauthorized scraping, stale feed, multiple downstream copies of same source, duplicate IOM polling | Source registry and `/ops/data-status`; per-handle X health exists; current IOM and RSS failures demonstrate coverage loss | Make one collector owner per source, use governed fixed-origin clients, persist last successful source timestamp and coverage-break rows, remove duplicate IOM job |
| Transport and buffering — AIS durable spool, DB queue, radio queues, HTTP clients | Protocol frames/messages → bounded work units | Queue saturation, partial replay, process-local locks, network redirects/SSRF, duplicate delivery | AIS spool receipt migration and tests; outbound policy metrics; radio drop/reset counters | Move NAVTEX cache/rate gate to Redis before multi-process; add queue age/high-water alarms and dead-letter inspection |
| Raw observation — `SourceObservationDB`, `VesselTrackDB`, radio/satellite tables | Source record → immutable-ish row/hash/reference | Some paths still write `IntelEvent` directly; raw bytes often absent; differing timestamp semantics; database timezone-naive serialization | Idempotency indexes and payload hashes; 24 h raw count available | Adopt Evidence Envelope v1 at adapter boundary; add explicit provider/source type/ingested/processed timestamps; immutable raw object only when rights/retention permit |
| Validation/normalization — adapters and domain contracts | Provider schema → canonical event | Broad exceptions collapse distinct provider/schema failures; malformed destination and stale static fields pass through | Pydantic and JSON-schema tests are extensive but adapter-specific coverage is uneven | Fail closed with typed error reason, preserve original field and normalized field, reject placeholders such as `LAST UPDATE TIME` as a declared destination |
| Entity resolution — vessel registry, `core.mda.identity`, entity graph | MMSI/IMO/name/flag → canonical subject/relationships | MMSI collision, stale registry cache, name-only sanctions false positives, shared upstream mistaken as independent | IMO validation and identity tests; no current operational conflict queue in public status | Store time-bounded identity assertions and conflicts; do not overwrite one identity with another; exact IMO/MMSI before name similarity |
| Geospatial processing — MDA reference, coverage, drift, track logic | WGS84 fixes/model fields → distances, areas, episodes | Joining incompatible fixes creates land-crossing lines; EPSG confusion; interpolation over gaps; NoData treated as zero | XT regression, drift suites, MapLibre split logic; server dossier still emitted one LineString | Server-side segment at impossible speed/gaps; explicit EPSG:4326 and geodesic method; version land/port/bathymetry reference layers |
| Correlation/classification — fusion, lineage edges, episodes/hypotheses | Observations/features → candidate analytical outputs | URL diversity mistaken for source independence; repeated derived AIS signals inflate evidence; missing hard negatives; automatic intent inference | Lineage/negative-control specs and replay scenarios; public status exposes counts | Independence groups must reflect upstream origin; preserve contradictions; benchmark at least 20 reviewed positives and 20 hard negatives before changing publication thresholds |
| Storage/archive — PostgreSQL, Redis, object store | Hot rows/cache/artifacts → query and retention | Missing query plans; Redis loss; R2 TLS/restore unverified; checksum readback mistaken for restore; deletion risk | 32 Alembic head, indexes, fault-injection/concurrency tests; application says PostgreSQL/Redis healthy | Keep AIS retention disabled. Require real two-session PostgreSQL + S3-compatible fault injection + full restore/replay + manifest reconciliation before release authorization |
| API — FastAPI routers/lifespan | DB/cache/runtime → operator and public contracts | Older deployment, inconsistent auth, broad exception fallback, large unbounded dossier payloads, process-local status | Health/ready/status/ops endpoints and contract tests; single-sample latency only | Exact-SHA deployment evidence, auth negative tests against public host, pagination/limits, OpenTelemetry spans and query timings |
| LIVE/PLAY/FUTURES — web + API projection | Canonical outputs → maps/timelines/models | Map draws inferred route, stale state presented as live, model shown as observation, map worker/static asset failures | 122 LIVE tests passed locally; earlier MapLibre worker regression has tests | One visual grammar: observed point, unobserved gap, derived corridor and modeled prediction are distinct layers and legends; FUTURES must carry training/cycle/method provenance |
| Publication/dossier — review records, public policy | Reviewable evidence → public claim | Missing published timestamp/processing version, sensitive humanitarian geometry, reviewer state not tied to exact evidence snapshot | ReviewRecord and publication gates exist | Require Evidence Envelope lineage completeness, privacy tier and exact evidence snapshot hash before publication |

## 5. FastAPI, scheduler and worker lifecycle

`core.api.main` uses a lifespan to bootstrap shared services and the scheduler; shutdown is delegated to `core.api.lifecycle`. `core.bootstrap` is also used by the standalone intelligence worker. This permits an API/worker split, but the current public operations summary shows the scheduler running in the API runtime and `job_execution_mode=queue`; deployment topology must be recorded so two replicas do not run the same singleton collector.

APScheduler intervals found in source: incident watch 5 m; darkship cue 10 m; source health/humanitarian reconcile/SAR enrichment/cross-modal closure/catalog recompute/AIS coverage snapshots 15 m; news/NAVAREA/hypothesis expiry/satellite 30 m; IOM 1 h; review/baselines/forensic/receiver discovery 6 h; MDA daily 24 h; reference refresh 14 d.

`news_monitor._poll_iom` and scheduler `_job_iom_incidents` independently call variants of the removed IOM endpoint every hour. This is duplicate work, duplicate event logic and duplicate failure noise. One adapter and one owner are required.

## 6. PostgreSQL, indexes, migrations, Redis and archive

- Alembic has one head: `0032_ais_spool_receipts`. The repository includes baseline through source observations, claims/assessments, lineage/entity graph, satellite/radio/receiver catalogue, operator hot-path indexes, LIVE retention, AIS coverage and spool receipts.
- `VesselTrackDB` has `(mmsi, ts)` and `ts` indexes. `SourceObservationDB` has the delivery-key unique constraint, `(source_name, observed_at)` and `(raw_payload_hash, received_at)` indexes. Episode, review, lineage and entity paths have targeted indexes.
- The app exposes no `EXPLAIN (ANALYZE, BUFFERS)` evidence, table/index sizes, bloat, connection-pool saturation or slow-query distribution. These must be measured on a disposable/read-only production replica or through approved read-only SQL, not inferred from models.
- Redis is reported configured but queue depth, cache hit ratio, memory, eviction and reconnect behaviour are not exposed in the public status.
- AIS prune is correctly hard-disabled in code by `_RETENTION_RELEASE_AUTHORIZED=False`, plus explicit policy/environment gates. It writes and reads back a compressed object before SQL delete and has mock/fault tests. This is not a completed real restore gate.
- No canonical database table currently records AIS archive object manifests, expected row ranges and restore outcomes as queryable operational evidence. Object-key naming and hashes in code are insufficient for end-to-end archive completeness.

## 7. Professional evidence model

The new contract `docs/contracts/evidence-envelope-v1.schema.json` implements the requested vocabulary and fields. It distinguishes:

- `observation`
- `official_report`
- `independent_corroboration`
- `algorithmic_inference`
- `modeled_prediction`
- `unverified_claim`
- `missing_data`
- `collection_failure`

It requires source/provider identity, original URL, raw reference and SHA-256, UTC observation/receipt/ingest/process/publication timestamps, WGS84 point plus uncertainty, identity confidence, independence group/count, method and processing versions, limitations, lineage parents and collection state.

Current `SourceObservationDB` covers much of the raw layer (`source_name`, `source_id`, URL, observed/received time, payload hash/reference, point/uncertainty, subject refs, provenance, schema and preservation status). Missing as first-class fields are provider/source type, ingested/processed/published times, identity confidence, independence group/count, method/processing version and limitations. Do not add a parallel truth table. Migrate/extend the canonical observation model and project the JSON contract at API boundaries.

Chronology validation must be explicit: `observed_at <= received_at <= ingested_at <= processed_at <= published_at` when the semantics exist. Backfills and provider corrections should create versioned assertions rather than rewriting the original observation.

## 8. XT EXPLORATION regression investigation

Subject: MMSI `249207000`, IMO `1043023`.

### What the current production evidence shows

- A 96-hour dossier returned 248 AIS track points.
- Ninety-six rows reused exactly `36.4734, 14.7783` from 02:55:16 through 14:41:39 UTC on 18 November while another sequence moved north/east and then west toward Augusta.
- The two sequences alternate under the same normalized source label `aisstream`. Several duplicate offshore rows report the same SOG/COG/heading while their receive times continue to change.
- The mandatory 10:21:33 → 10:32:44 regression pair is about 89.5 km in 671 seconds, around 260 knots. The current production dossier also contains a 10:21:33 Augusta-area fix followed at 10:24:44 by the repeated offshore coordinate, an even shorter incompatible adjacency.
- Production emits all 248 points as one LineString and therefore draws many false straight connections. Production does not expose #543 `track_discontinuities` because it is on an older revision.
- One derived Barcelona port stay earlier in the window is supported by multiple slow fixes. It has no evidentiary bearing on the conflicting 18 November sequences.

### Supported conclusion

The retained records are internally inconsistent for a single physical vessel trajectory. They demonstrate a track-integrity/entity-resolution problem. They do **not** establish spoofing, illicit conduct, a hidden port call or the exact sailed route.

Plausible hypotheses that remain open:

1. two transmitters or identities using the same MMSI;
2. an upstream stale/replayed position stream fused with a current stream;
3. a provider or local normalization/deduplication error;
4. inconsistent source timestamp versus receipt timestamp ordering;
5. wrong vessel identity attribution for one sequence.

The normalized `source=aisstream` label is insufficient to discriminate these. Resolution requires raw message reference/hash, AIS message type, provider event timestamp, received/ingested timestamps, upstream connection/session lineage, static identity messages and independent receiver/provider comparison.

### Implemented regression hardening

- PostgreSQL track timestamps are serialized with explicit UTC offsets. Without this, #543 rejected production-style naive timestamps and reported zero valid fixes.
- The server dossier now emits only contiguous plausible LineString runs. It splits at invalid order, a 30-minute unobserved interval or implied speed above 45 knots. Singleton fixes remain in `track_points` and no false line is drawn through them.
- Each displayed line says `is_observed_route=false`, `evidence_level=adjacent_ais_fixes_only` and carries the method version.
- The detector still preserves input order and flags out-of-order pairs; it does not sort away evidence of ingestion disorder.

## 9. MINSTREL: gap versus forecast

Subject: MMSI `305064000`, IMO `9195561`.

At 18:19 UTC the 14-day dossier contained 263 observations. The last retained observation was 17 November 20:48:14 UTC at approximately `36.9136, 14.0590`, about 45.5 hours old. No current MINSTREL public LIVE signal or retained seven-day MDA anomaly was returned by the sampled endpoints. The static destination value was `LAST UPDATE TIME`, which is a malformed placeholder, not a declared destination. Production exposed no discontinuity contract.

SeaCommons therefore cannot defensibly publish a modeled corridor or ETA for this snapshot. The correct product contract is:

| Public field | Evidence class | Rule |
|---|---|---|
| Last verified position | `observation` | Coordinates and observation timestamp from retained AIS, with provider/source lineage |
| Observation age | derived display field | `now - observed_at`, plus receipt age separately when needed |
| Coverage state | `missing_data` or `collection_failure` | Gap only within the named acquisition system and its expected coverage profile |
| Declared destination | `observation` | Raw AIS destination plus source/time; reject placeholders and never geocode silently |
| Expected corridor | `modeled_prediction` | Only after destination resolution and calibrated route model; polygon/corridor, method version and confidence |
| ETA window | `modeled_prediction` | Range, not point estimate; model cycle, assumptions and error distribution |
| Third-party forecast | `official_report` or `modeled_prediction` from that provider | Clearly attributed; never converted into a historical observed position |

An AIS gap means “SeaCommons did not retain a recent observation under the stated coverage conditions.” A forecast means “a model expects future movement.” Neither proves the other, and a forecast is never a synthetic track point.

## 10. Implemented changes in the isolated branch

1. Migrated the external NAVTEX adapter from direct `urlopen` to the governed fixed-origin client with bounded response contract, DNS/redirect policy and observability.
2. Made the outbound-HTTP adoption scanner explicitly UTF-8 on Windows.
3. Updated stale radio/config tests to assert the intended fail-closed semantics rather than historical exact capacity.
4. Added UTC-explicit vessel-track serialization and evidence-safe server-side track segmentation.
5. Removed unreviewed raw receiver endpoint labels from the public mesh rows.
6. Added Evidence Envelope v1 JSON Schema and contract tests.
7. Replaced the POSIX-only AIS spool disk-space check with a cross-platform, fail-closed implementation; the full suite now exercises the durable spool on Windows as well as Linux CI.

No deployment was performed. The changes are not production functionality until review, full CI, exact-SHA deployment and live verification succeed.

## 11. Severity-ranked findings

### P0 — release/security/evidence integrity

1. Reconcile and deploy an exact reviewed SHA; production is not current main and exposes a route that current main protects with roles.
2. Stop public exposure of unreviewed receiver URLs/IPs; verify the fix on the actual public mesh.
3. Repair or explicitly disable the broken IOM collector and remove duplicate polling. Coverage must be visibly offline until a functioning licensed endpoint exists.
4. Never render one XT EXPLORATION line across conflicting streams; deploy UTC serialization and server segmentation after CI.
5. Keep AIS retention disabled until real PostgreSQL/S3-compatible restore with failure injection, manifest reconciliation and replay is proven.

### P1 — analytical correctness and operations

1. Adopt the Evidence Envelope fields in the canonical observation model and public dossier.
2. Validate AIS destination values and separate declared destination, resolved place and model output.
3. Build upstream independence groups; provider count is not source independence.
4. Add time-bounded source coverage and expected-reception models to every gap.
5. Establish database query plans, endpoint percentile SLOs, Redis/queue metrics and disk/object-store alerts.
6. Resolve 95 JS lint warnings without increasing the warning budget.

### P2 — research expansion

Pilot the five sources selected in `DATA_SOURCE_REGISTRY_2026-11-19.md`, each behind licence, sample-fixture, failure and monitoring gates. Integrations must extend existing adapters and canonical models; do not create parallel source-of-truth tables.

## 12. Verification evidence

Completed locally in the isolated worktree:

- Full API/repository pytest suite: 2,200 passed, 3 skipped, 216 warnings in 8m08s.
- Focused safety/regression set after the final code changes: 57 passed.
- AIS prune and durable-spool fault/cross-platform set: 24 passed.
- Outbound HTTP bypass inventory: 28 entries, no delta.
- LIVE frontend suite: 122 passed.
- Production frontend build: passed; 1,755 modules transformed.
- `git diff --check`: passed.
- Alembic: one head, `0032_ais_spool_receipts`.
- Full JS lint: failed with 0 errors and 95 warnings because the repository enforces `--max-warnings 0`; the warning budget was not weakened.

Not completed and therefore not claimed: full hosted CI, lint cleanup, real PostgreSQL query plans, Redis inspection, Oracle disk/process inventory, R2 restore, deployment, or post-deploy browser/public verification.
