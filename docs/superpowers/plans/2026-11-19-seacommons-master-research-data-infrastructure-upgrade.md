# SeaCommons Master Research, Data Intelligence & Infrastructure Upgrade Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade SeaCommons into a continuously operating, evidence-lineage-first maritime intelligence platform while closing the current production drift, acquisition failures, AIS integrity defects and restore/observability gaps.

**Architecture:** Extend the existing canonical pipeline (`SourceObservation` → normalized event → episode/hypothesis → reviewed publication). Do not add parallel truth stores. Every new adapter uses governed fixed-origin transport, writes an Evidence Envelope-compatible observation, declares upstream independence, exposes coverage/health and fails closed. PostgreSQL remains canonical; Redis is cache/rate/coordination only; object storage holds bounded licensed artifacts referenced by immutable hashes.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy/Alembic, PostgreSQL, Redis, APScheduler/database queue, JSON Schema 2020-12, Vite/React/MapLibre, pytest/node:test/Playwright, Cloudflare R2-compatible S3, Vercel static/proxy deployment.

---

## Preconditions and non-negotiable gates

- Work only from a clean worktree based on current `origin/main`; reconcile open PRs and deployment SHA before editing.
- Do not reset, pull over, migrate, restart or prune the modified Oracle checkout.
- Keep `_RETENTION_RELEASE_AUTHORIZED=False` until Task 10 passes in real infrastructure.
- Never use provider count as independent-source count.
- Never publish a predicted point as a historical observation or draw a line through an unobserved/impossible interval.
- Do not activate a source before endpoint sample, terms, redistribution, sensitivity and monitoring gates pass.

### Task 1: Land the current regression/security patch behind exact tests

**Files:**

- Modify: `apps/api/core/radio/external_navtex.py`
- Modify: `scripts/check_outbound_http_bypasses.py`
- Modify: `apps/api/core/vessels/track_store.py`
- Modify: `apps/api/core/mda/track_discontinuity.py`
- Modify: `apps/api/core/api/routes/mda.py`
- Modify: `apps/api/core/radio/catalog_store.py`
- Modify: `apps/api/core/vessels/track_spool.py`
- Modify tests already changed in `tests/` and `apps/web/src/features/live/radioMap.test.js`
- Add: `docs/contracts/evidence-envelope-v1.schema.json`

**Step 1: Rebase/recreate on the latest clean `origin/main` and inspect the diff.**

Run: `git fetch origin --prune` then `git diff --check origin/main...HEAD`.

Expected: no unrelated generated assets, secrets or changes from the modified local main checkout.

**Step 2: Run the focused safety tests.**

Run:

```powershell
$env:PYTHONPATH='apps/api'
python -m pytest tests/test_external_navtex.py tests/test_external_navtex_snapshot.py tests/test_outbound_adoption_guard.py tests/test_mda_track_discontinuity.py tests/test_receiver_catalog_persistence.py tests/test_radio_live_dossier.py tests/test_track_store.py tests/test_evidence_envelope_contract.py -q
python scripts/check_outbound_http_bypasses.py
Push-Location apps/web; npm.cmd run test:live; Pop-Location
```

Expected: all pass; outbound inventory has no new bypass.

**Step 3: Add a negative public-mesh API test.**

Write a failing test that inserts an unreviewed URL-labelled receiver and calls `/api/v1/live/receivers/mesh`; assert neither hostname nor IP appears anywhere in the JSON. Confirm red, then make only the smallest projection fix and confirm green.

**Step 4: Commit as one reviewable patch.**

Suggested message: `fix(evidence): close track, receiver and outbound integrity regressions`.

### Task 2: Establish release identity and close the production auth drift

**Files:**

- Modify: `tests/test_security.py` or add `tests/test_mda_route_auth.py`
- Modify only if required: `apps/api/core/api/routes/mda.py`, proxy routing configuration
- Add: `docs/release/PRODUCTION_BASELINE_<date>.md`

**Step 1: Write auth negative controls.**

Test `/api/v1/mda/vessel/{mmsi}` without credentials, with an invalid token and with a valid read role. Expected: 401/403/200. Test both direct FastAPI and the Vercel proxy route contract.

**Step 2: Read the current Oracle deployment non-destructively.**

Record service unit/container, exact git SHA/image digest, environment names without values, worker count, scheduler owner and upstream host. Do not change anything.

**Step 3: Compare production SHA with the reviewed SHA and PR #543–#546.**

Stop if the deployment source contains uncommitted or unexplained changes. Choose a clean artifact/image deployment; do not pull into the dirty checkout.

**Step 4: Deploy only through the canonical workflow.**

Capture build URL, immutable SHA, health/ready response and rollback artifact. Verify the unauthenticated dossier is denied on the public hostname.

### Task 3: Make source health and coverage first-class

**Files:**

- Modify: `apps/api/core/intel/source_registry.py`
- Modify: `apps/api/core/acquisition/status.py`
- Modify: `apps/api/core/api/routes/ops.py`
- Modify: `apps/api/core/intel/news_monitor.py`
- Modify: `apps/api/core/scheduler.py`
- Add tests: `tests/test_source_coverage_runtime.py`, adapter tests

**Step 1: Write a failing duplicate-owner test.**

Assert exactly one scheduled owner exists per external source. The test must fail because IOM exists in both `news_monitor` and `_job_iom_incidents`.

**Step 2: Consolidate IOM into one adapter and one schedule.**

Keep source status offline when the official endpoint is 404/400. Do not scrape the ArcGIS map. Remove the duplicate job only after the remaining owner reports error class, last success, last attempted endpoint and next retry.

**Step 3: Persist coverage transitions.**

Write `SourceCoverageEventDB` rows only on state/method changes (`added`, `removed`, `method_changed`, `coverage_break`, `restored`). Include profile version and rationale; do not create one row per poll.

**Step 4: Add alert thresholds.**

Alert on source-specific freshness expectations, not aggregate “operational”. Required current gates: IOM offline, RSS 404, NGO AIS timeout, NAVAREA staleness, radio active/desired divergence.

### Task 4: Adopt Evidence Envelope v1 in the canonical model

**Files:**

- Modify: `apps/api/core/db/models.py`
- Add: `apps/api/core/db/migrations/versions/0033_evidence_envelope_fields.py`
- Modify: `apps/api/core/intel/source_observation.py`
- Add: `apps/api/core/intel/evidence_envelope.py`
- Modify: `docs/contracts/evidence-envelope-v1.schema.json`
- Add tests: `tests/test_evidence_envelope_model.py`, chronology tests

**Step 1: Write failing model/chronology tests.**

Require provider, source type, ingested/processed/published UTC timestamps, independence group/count, identity confidence, method/processing version and limitations. Negative controls: naive time; observed after receipt; publication before processing; unknown evidence level; independent count larger than distinct lineage groups.

**Step 2: Add nullable migration fields with no table rewrite where possible.**

Deploy schema first. Backfill deterministic fields in bounded batches. Do not invent unknown timestamps; null means unknown.

**Step 3: Make adapter writes produce the contract.**

Record raw provider payload before normalization when rights allow. Otherwise record a deterministic hash and restricted reference with an explicit limitation.

**Step 4: Add lineage completeness metrics.**

Expose counts/percentages of observations, hypotheses and published items missing required lineage. Publication gate target: 100% for new public dossiers.

### Task 5: Resolve AIS stream conflicts and timestamp provenance

**Files:**

- Modify: `apps/api/core/vessels/ais_source_observation.py`
- Modify: `apps/api/core/vessels/track_store.py`
- Add: `apps/api/core/mda/track_lineage.py`
- Modify: `apps/api/core/mda/track_discontinuity.py`
- Add fixture: `tests/fixtures/ais/xt_exploration_conflicting_streams.jsonl`
- Add tests: `tests/test_mda_track_lineage.py`

**Step 1: Create an evidence-safe XT fixture.**

Include the known 10:21:33/10:32:44 pair, repeated offshore fixes, moving Augusta-area fixes and source/receipt timestamps. Use only already public/non-sensitive fields and preserve exact UTC.

**Step 2: Write failing conflict tests.**

Expected: two incompatible candidate stream clusters, no joined route, no spoofing assertion, raw-source lineage required, and a deterministic `identity_conflict_or_upstream_fusion` review state.

**Step 3: Preserve timestamp layers.**

Store provider/source timestamp, received, ingested and processed separately. Never replace provider time with receipt time silently. Mark out-of-order ingestion without sorting it away.

**Step 4: Add conflict-aware projection.**

Map each candidate stream with a separate style and uncertainty; show conflicting observations as observations, not one route. Dossier text must list open hypotheses and required corroboration.

### Task 6: Implement observation/gap/forecast separation for MINSTREL

**Files:**

- Add: `apps/api/core/domain/vessel_movement_contract.py`
- Modify: `apps/api/core/api/routes/mda.py`
- Modify: `apps/web/src/features/live/vesselPresentation.js` and tests
- Add: `docs/contracts/vessel-movement-v1.schema.json`

**Step 1: Write contract tests.**

Test last observed point/time, observation age, receipt age, coverage profile/state, raw declared destination and validity, resolved destination provenance, modeled corridor polygon, ETA window, model cycle/method and limitations.

**Step 2: Reject destination placeholders.**

`LAST UPDATE TIME`, empty/unknown values and timestamps are invalid destinations. Preserve the raw value for lineage but publish declared destination as unavailable.

**Step 3: Implement abstention first.**

For the current MINSTREL fixture, expected forecast state is `unavailable_insufficient_destination_evidence`. Do not generate a corridor or ETA.

**Step 4: Pilot prediction only against historical holdout voyages.**

Measure corridor containment, ETA absolute error and calibration by horizon/vessel class. Publish a range only after thresholds are approved; prediction remains a separate layer.

### Task 7: Integrate the first public/open data pilots

**Files:**

- Add adapters under `apps/api/core/connectors/` or extend the existing canonical connector package
- Add fixtures under `tests/fixtures/sources/`
- Modify: `apps/api/core/scheduler.py`, source registry, observability
- Update: `docs/research/DATA_SOURCE_REGISTRY_2026-11-19.md`

Implement in this order, one source per PR:

1. MeteoAlarm OGC EDR/CAP.
2. EMODnet bathymetry reference snapshot.
3. EMODnet vessel-density reference snapshot.
4. UNSC consolidated XML direct-source check.
5. Algeria WIS2 station/observation pilot.

For every source: failing fixture parser test; fixed-origin transport; conditional request/ETag; bounded payload; schema validation; raw hash/reference; rights metadata; independence group; retry/dead-letter; freshness metric; public projection negative controls; kill switch. Never query WMS/WCS on each user request—materialize versioned reference snapshots.

### Task 8: Database and query performance baseline

**Files:**

- Add: `scripts/audit_postgres_readonly.py`
- Add: `docs/audits/POSTGRES_BASELINE_<date>.md`
- Add tests for script redaction/read-only guarantees

**Step 1: Prove the audit script is read-only.**

Allow only `SELECT`, `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` on bounded queries and catalog views. Reject semicolons/multiple statements and any write keyword.

**Step 2: Measure representative queries.**

Cover LIVE 24 h, vessel track by MMSI/time, source-observation lineage, episode publication, radio associations and status aggregates. Record plan, rows, buffers, p50/p95 from repeated runs, table/index sizes and connection pool.

**Step 3: Fix only measured bottlenecks.**

Use migrations for indexes; validate write amplification and query improvement. Do not add a graph database until measured relational queries justify it.

### Task 9: Redis, queues, retries and dead letters

**Files:**

- Modify: job/queue and observability modules after locating canonical owners
- Add: `tests/test_queue_failure_modes.py`
- Update operations docs/runbook

Add queue depth, oldest age, retry count, dead count, worker heartbeat and Redis reconnect/eviction metrics. Failure tests: Redis absent, PostgreSQL transient failure, duplicate delivery, poison job and worker crash. Ensure collectors degrade independently and no source outage blocks `/health` while `/ready` accurately reflects required dependencies.

### Task 10: Prove AIS archive restore before retention

**Files:**

- Add canonical archive manifest model/migration only after design review
- Add: `scripts/restore_ais_archive.py`
- Extend: `tests/test_ais_archive_pg_concurrency.py`
- Add: `docs/runbooks/AIS_ARCHIVE_RESTORE.md`

**Step 1: Run disposable real PostgreSQL + S3-compatible storage.**

Use two concurrent prune workers, conditional create-only object writes, network timeout after PUT, corrupt GET, partial object, duplicate batch and SQL delete mismatch.

**Step 2: Restore into a fresh database.**

Verify manifest object count, compressed and uncompressed hashes, row count, ID/time range, schema version and replay idempotency. Compare restored rows field-for-field.

**Step 3: Perform an operator-reviewed R2 drill.**

Record bucket/object version, restore duration and evidence. Only then consider changing `_RETENTION_RELEASE_AUTHORIZED`; environment variables alone remain insufficient.

### Task 11: Frontend evidence grammar and accessibility

**Files:**

- Modify LIVE/PLAY map layer builders and legend components
- Add node tests and Playwright screenshots

Use distinct symbols/styles for observed fix, unobserved interval, conflicting stream, official report, algorithmic inference and modeled corridor. NoData must differ from zero. Display observation time and source coverage next to gap age. Test mobile/desktop, color-vision-safe palette, keyboard access and map/list consistency.

### Task 12: Full release qualification and monitored deployment

**Step 1: Run full gates.**

```powershell
$env:PYTHONPATH='apps/api'
python -m pytest -q
python scripts/check_outbound_http_bypasses.py
Push-Location apps/web
npm.cmd ci
npm.cmd run lint:js:full
npm.cmd run test:live
npm.cmd run build
Pop-Location
git diff --check
```

Expected: zero failures and zero lint warnings. Do not change warning thresholds.

**Step 2: Deploy exact SHA and record evidence.**

Verify API revision, Vercel deployment, health/ready, auth denial, source health, radio privacy, XT segmentation, MINSTREL abstention, LIVE/PLAY rendering and status counters.

**Step 3: Observe for one full collector cycle.**

Minimum 60 minutes for hourly sources and longer for source-specific cadence. Confirm no duplicate polling, growing queue, 404 loop, raw endpoint leakage or model/observation conflation.

**Step 4: Publish completion evidence.**

Report exact SHA/URL/time, tests, production probes, remaining known limits and rollback result. Never claim integration, monitoring or archive safety without the corresponding evidence.
