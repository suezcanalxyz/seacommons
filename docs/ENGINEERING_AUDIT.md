# SeaCommons Engineering Audit

Date: 2026-08-25
Scope: PHASE 0 baseline audit per `docs/roadmap.md`. Read-only — no implementation changed.
Method: repository structure walk (296 tracked files), line-count sampling of largest modules,
close reading of security/config/CI/entrypoint/live-realtime code, existing docs cross-checked
(`README.md`, `SECURITY.md`, `CONTRIBUTING.md`, `docs/*AUDIT*.md`).

Findings are classified:
- **P0** — security / data correctness
- **P1** — architecture / reliability
- **P2** — maintainability / testing
- **P3** — polish / documentation

---

## 1. Current Architecture

Monorepo, four deployable surfaces plus a research/prototype surface:

```
apps/api/     FastAPI backend (Python 3.11+): routes, domain logic, workers, drift engine,
              forensic pipeline, sensor ingestion, intel monitors — mostly undifferentiated
              inside one `core/` package.
apps/web/     React 19 + Vite operational console (Cesium 3D globe + MapLibre), JS/JSX,
              partial TypeScript config (tsconfig present, code still .jsx).
apps/edge/    Cloudflare Worker + Durable Object ("LiveRoom") — the public realtime relay.
apps/site/    Static institutional site (plain HTML/CSS/JS), separate from the console.
apps/unreal/  Unreal Engine "Immersive" pixel-streaming prototype — experimental, not part
              of the operational path.
deploy/       Docker/nginx/systemd deployment manifests.
docs/         13+ audit/runbook/plan docs already exist (see §Documentation debt).
```

Three independent runtimes ship to production: the FastAPI console API, the Cloudflare edge
worker (public Live), and the static site. They are loosely coupled via HTTP (the API pushes
signed events to the edge via `core/live_edge_publisher.py`; the edge never calls back into
the API).

## 2. Application Boundaries

- **Operational console** (`live.seacommons.org`, authenticated): full FastAPI surface,
  OIDC-gated, backed by Postgres/SQLite.
- **Public demo** (`play.seacommons.org`): same FastAPI codebase, `DEMO_PUBLIC_MODE=true`
  disables mutating routes at the middleware layer (`apps/api/core/api/main.py:122`).
- **Public Live** (edge worker, `apps/edge/src/live.js`): a deliberately narrower,
  privacy-filtered projection of a subset of intel events — no direct DB access, receives
  only what `core/api/routes/live.py` and `core/live_edge_publisher.py` choose to forward.
- **Institutional site** (`apps/site/`): fully static, no backend dependency.

The boundary between "operational" and "public" is enforced in at least three independent
places with three different rule sets: the FastAPI `authorization_gate` middleware
(`main.py:118-155`), the `_public_intel_feature` allow-list in `routes/live.py:62-127`, and
the edge worker's own `visibility === 'public'` check (`live.js:208`). See §13 (risky implicit
contracts) — this triplication is the single biggest correctness risk in the repo.

## 3. Backend Structure

`apps/api/core/` (21,843 LOC across ~140 `.py` files) is a single flat-ish package with loose
subject-based folders (`intel/`, `drift/`, `ingestion/`, `integrations/`, `sensors/`,
`probability/`, `forensic/`, `vessels/`, `zones/`, `chokepoints/`, `anomaly/`, `ocean/`,
`rendering/`) but no consistent layering. There is a `core/domain/events.py` but most business
logic actually lives inside route modules or inside "store" singletons (`core/intel/store.py`,
`core/db/store.py`) rather than a dedicated service layer. `core/api/routes/*.py` mixes
request parsing, authorization detail, DB queries, and domain interpretation in the same
functions (see §14).

## 4. Frontend Structure

`apps/web/src/` is effectively three files:

| file | LOC |
|---|---|
| `apps/web/src/main.jsx` | 3376 |
| `apps/web/src/styles.css` | 3218 |
| `apps/web/src/components/PlayCesium.jsx` | 1230 |
| `apps/web/src/components/IntelDashboard.jsx` | 964 |

`main.jsx` is the app shell, router, most data fetching, most websocket/SSE handling, and
most feature logic combined — it is the frontend's single largest architectural liability.
Smaller components (`CasesWorkspace.jsx` 123 LOC, `ConnectorWorkspace.jsx` 244 LOC) show the
target granularity is already understood elsewhere in the codebase; it just wasn't applied to
the main shell or the two largest feature surfaces (Cesium map, Intel dashboard).

No `features/`, `services/`, or `domain/` directories exist yet. `apps/web/src/simulation/`
is the one area that already has the shape the roadmap wants (`contracts.js`, `driftEngine.js`,
`sceneAdapter.js`, `workerClient.js`, with `.test.js` files) — treat it as the internal
precedent for Phase 1/7, not as something to rebuild.

## 5. Edge/Runtime Components

`apps/edge/` is a Cloudflare Worker (`wrangler.jsonc`) exporting a single Durable Object,
`LiveRoom` (`apps/edge/src/live.js`, 321 LOC). It owns:
- HMAC-verified ingestion (`verifyIngestRequest`, timing-safe compare, `live.js:29-36,68-81`)
- WebSocket fan-out via `state.acceptWebSocket` (hibernatable DO WebSockets)
- TTL-based event expiry (`isFresh`, default 8 days) and per-incident version replacement
  (`ingest()`, `live.js:213-221`)
- Source-health heartbeats with staleness downgrade to `"offline"` (`loadSourceHealth`,
  `live.js:304-315`)
- Optional snapshot mirror to R2 (`env.LIVE_SNAPSHOTS`) and an optional Nostr bridge fan-out

This is a genuinely well-built small module (see §Strengths) but it is the *only* realtime
correctness boundary on the public side — there is no edge-side test for concurrent
Durable-Object instances, multi-region replay, or WebSocket reconnect/backfill ordering beyond
`apps/edge/src/live.test.js` (71 LOC, unit-level only).

## 6. Workers / Background Jobs

`apps/api/core/`: `scheduler.py` (391 LOC, APScheduler-based), `worker.py` / `worker_service.py`
(job queue consumers), `jobs.py`, `intel_worker_main.py` (standalone process entrypoint for
split deployments). `core/bootstrap.py` starts background sensors, the intel engine, and the
scheduler in-process during FastAPI's `lifespan` unless `INTEL_MONITORS_ENABLED=false`, in
which case a second process is expected to run them and this process instead polls the DB
every 30s (`main.py:90-104`). This split-deployment mode is real but only documented in code
comments, not in `docs/ARCHITECTURE.md` — a reviewer reading only the docs would not know two
process topologies exist.

`JOB_EXECUTION_MODE` (`inline` vs `queue`) changes whether jobs run synchronously in the web
process or via a queue — `config.py:77`, gated further by `validate_production_security()`
requiring `queue` mode in production (`security.py:130`). This is exactly the kind of
"implicit until you grep for it" contract the roadmap wants made explicit (Phase 4/9).

## 7. Databases and Storage

- **Primary**: SQLAlchemy ORM over Postgres in production, SQLite (`aiosqlite`) for
  dev/tests (`core/db/session.py`, `core/db/models.py`).
- **Models are append-only-by-convention** (`ForensicEvent`, `AnomalyEvent`, `DriftResultDB`,
  `AlertEvent` — `db/models.py:15-79`) but nothing at the DB layer enforces immutability
  (no triggers, no `INSERT`-only grants) — it's a documented convention, not a constraint.
- **Object storage**: MinIO/S3-compatible via `core/object_store.py`, configured through
  `OBJECT_STORAGE_*` settings; required in production (`security.py:128`).
- **Edge storage**: Durable Object transactional KV storage (`state.storage`) plus optional
  R2 bucket mirror (`env.LIVE_SNAPSHOTS`) — a second, independent storage system with its own
  consistency model (per-DO single-writer) that never talks to Postgres directly.
- **In-memory caches**: `core/intel/store.py` (924 LOC) is an in-process singleton store that
  is also periodically reloaded/synced from the DB (`intel_store.load_from_db()`,
  `sync_from_db()` — `main.py:55-56,100`) — a cache-coherence surface with no visible
  invalidation tests.

## 8. Realtime/Event Architecture

Flow: sensors/intel monitors → `core/intel/store.py` (in-memory) → DB persistence →
`core/live_edge_publisher.py` (523 LOC) → HMAC-signed push to the Cloudflare edge worker →
`LiveRoom` Durable Object → WebSocket fan-out to browsers. A parallel path serves the
authenticated console directly from the FastAPI process (its own WebSocket/REST, not shown to
go through the edge).

This is a federated, at-least-once, idempotent-by-id design (`event.id` de-dup check,
`live.js:210-211`) with per-incident version replacement — a defensible architecture. But
**the invariants the roadmap calls out in Phase 5 are asserted only in code comments, not in
tests that would fail if violated**:
- "resolved incidents must never return to active Live accidentally" — enforced by the
  `removed` flag path (`live.js:220-221`) and by `_public_intel_feature`'s publication-status
  check (`routes/live.py:79-84`), but no test asserts that a stale/racing publish cannot
  resurrect a resolved incident.
- "unverified coordinates must never be fabricated" — enforced by
  `_approximate_public_point`'s deterministic *displacement* (not fabrication) of real
  coordinates (`live.js` has no equivalent; this lives in `core/intel/public_geometry.py`,
  not read in this pass — flag for Phase 4/5 follow-up).
- "stale source health must not be interpreted as fresh" — enforced (`loadSourceHealth`
  downgrades to `offline` past `maxAge`), and this one path *does* look correctly built.

No test in `tests/` or `apps/edge/*.test.js` exercises **duplicate delivery under concurrent
ingest**, **out-of-order `observed_at`**, or **process-restart recovery of `head_hash`
continuity** — these are named directly in Phase 5 of the roadmap and are presently unverified.

## 9. External Integrations

`core/integrations/` (AIS via aisstream.io, TimeZero bridge, generic webhook router),
`core/ingestion/channels/` (Telegram, Twilio SMS/WhatsApp, Meta WhatsApp Cloud API, generic
webhook), `core/intel/twikit_monitor.py` (1065 LOC — largest single file in the backend,
unofficial X/Twitter scraping via cookie-authenticated session), `core/ocean/cmems.py`
(Copernicus Marine), Open-Meteo weather, GDACS, ACLED, GPSJam, EMSC seismic websocket,
Madrigal ionosphere. This is a wide integration surface (11+ external providers) with highly
uneven trust levels — official APIs, RSS/webhooks, and an explicitly-labeled `unofficial`
scraper (twikit) coexist, distinguished only by the `source_policy` string field. Config
comments (`config.py:175-180`) show the team is already aware `source_policy="unofficial"` is
the mechanism keeping twikit data off the public map — this is exactly the kind of "single
canonical definition" the roadmap's Phase 4 wants formalized as a type, not a convention.

## 10. Security Model

- **AuthN**: OIDC/JWT (Keycloak reference), `core/security.py` (133 LOC) — JWKS fetched and
  cached 300s (`_load_jwks`), RS256/ES256 only, `exp`/`iat`/`sub` required. WebSocket auth
  uses the Sec-WebSocket-Protocol subprotocol trick to smuggle a bearer token pre-accept
  (`authorize_websocket`, `security.py:86-102`) — a legitimate, if unusual, pattern; worth a
  one-line doc note since it's non-obvious to a reviewer.
- **AuthZ**: coarse role sets (`WRITE_ROLES`, `READ_ROLES`) checked centrally in one
  middleware (`main.py:118-155`) rather than per-route decorators — good for auditability
  (one place to read the whole policy) but every new route's exposure is decided by a path
  string match in that middleware, which is easy to get wrong silently (no test in `tests/`
  enumerates "every route not explicitly public requires auth" as an invariant — **P1**).
- **Ingestion authenticity**: HMAC signature verification duplicated in two languages — Python
  (webhook channels) and JS (`apps/edge/src/live.js` `verifyIngestRequest`) — both use
  timing-safe comparison, but there is no shared contract test proving both sides agree on the
  HMAC construction (canonicalization, encoding) — **P1**, silent drift risk between the two
  implementations if one changes.
- **Fail-safe production config**: `validate_production_security()` (`security.py:118-133`)
  is a genuine strength — a real hard-fail if `RUNTIME_PROFILE=production` and
  `AUTH_ENABLED`/`OIDC_ISSUER`/`OIDC_AUDIENCE`/`OBJECT_STORAGE_ENDPOINT`/
  `JOB_EXECUTION_MODE=queue` aren't all set. This is the kind of explicit contract the roadmap
  wants more of.
- **CORS**: explicit origin allow-list plus a `*.vercel.app` regex (`main.py:162-176`);
  `allow_credentials=False` is correctly paired with a wildcard-capable config, with a comment
  explaining *why* (Starlette raises otherwise) — good practice, keep as-is.

**P0 candidates found, not yet verified as exploitable (flag for Phase 6, do not fix in this
pass):**
- `_jwks_url()` / `_load_jwks()` use raw `urllib.request.urlopen` with a 5s timeout and no
  explicit TLS/cert pinning beyond what urllib defaults provide (`security.py:44-52`) — low
  risk given it's operator-configured, but worth a `nosec` comment already present acknowledging
  it (`security.py:49`) — someone already flagged this; no action needed beyond documenting the
  accepted risk in `SECURITY.md`.
- `docs/.env.example` (217 lines) lists ~15 secret-shaped variables all left empty — correct
  practice, no secrets committed. Confirmed clean.

## 11. Auth/Authz Model

Covered in §10. Additional note: `MOCK` and `DEMO_PUBLIC_MODE` are two different "reduced
capability" flags with different scopes (`config.py:148-149`) — `MOCK` is marked deprecated in
its own comment but still present in the settings class. **P3** — dead config surface, remove
once confirmed unused (grep before removing; do not remove in this audit pass per
"never invent functionality / preserve behaviour").

## 12. Observability

`core/observability.py` provides `configure_logging`, `metrics_middleware`,
`refresh_operational_gauges`, wired to a Prometheus `/metrics` endpoint (`main.py:213-218`).
`/health` (liveness) and `/ready` (DB connectivity check via `SELECT 1`, `main.py:201-210`)
both exist — good baseline. Not verified in this pass: whether worker/scheduler/source health
(AIS, twikit, GDACS, CMEMS) is exposed as its own gauge set, or only inferred indirectly — a
Phase 10 follow-up question, not answered here (do not guess).

## 13. Test Coverage

23 files under `tests/`, 209 `def test_*` functions (pytest, `pytest.ini` + `asyncio_mode =
auto`). Coverage is real but narrow relative to surface area: 21,843 LOC of backend Python vs.
209 tests. Named test files map to specific features (`test_live_edge_publisher.py`,
`test_live_resolved_visibility.py`, `test_drift_trajectory.py`, `test_security.py`,
`test_runtime_contracts.py`) — encouraging naming discipline, but several roadmap-flagged
files have **no corresponding test file at all**: `core/api/routes/intel.py` (633 LOC),
`core/intel/twikit_monitor.py` (1065 LOC), `core/intel/store.py` (924 LOC),
`core/drift/opendrift_pool.py` (912 LOC) — **P2**.

Frontend: `apps/web/src/simulation/*.test.js` (2 files, run via `node --test`, wired into CI).
No React component tests exist anywhere. `npm run lint` is aliased to `tsc --noEmit`
(`package.json:16`) — **there is no ESLint configured**, despite the script being named
`lint` — **P2**, misleading naming, and no actual JS/JSX lint rules are enforced (unused vars,
hooks-rules, etc. all unchecked).

Edge: `apps/edge/src/*.test.js` (2 files, `environment.test.js` 29 LOC, `live.test.js` 71
LOC) — thin relative to `live.js`'s 321 LOC and its stated realtime invariants (see §8).

## 14. CI/CD

`.github/workflows/ci.yml` — three parallel jobs (api/web/edge), all straightforward and fast.
Concretely:
- **api**: installs `apps/api[dev]` (which *does* declare `ruff` and `mypy` as dev deps in
  `pyproject.toml:50-51`) but CI **only runs `pytest -q`** — ruff and mypy are never invoked
  in CI despite being present in the dev extras — **P2**, dead tooling investment, easy fix.
- **web**: `npm ci` → `npm run lint` (= `tsc --noEmit`, not real linting, see §13) →
  `npm run test:simulation` → `npm run build`. No `tsconfig.json` `"strict": true` — checked,
  absent (`apps/web/tsconfig.json`) — **P2**, roadmap Phase 2 will need this eventually but
  don't flip it repo-wide in one PR (roadmap explicitly warns against big-bang conversions).
- **edge**: `npm ci` → `npm test`. Fine for its scope.
- **No dependency security scanning** anywhere: no `pip-audit`, no `npm audit`, no CodeQL
  workflow, no Dependabot/Renovate config found (`.github/` has only `workflows/`, no
  `dependabot.yml`) — **P0/P1** per roadmap Phase 6 (explicitly requested), currently absent
  entirely.
- A second workflow, `.github/workflows/alarm-phone-lifecycle.yml`, and a third,
  `federated-live.yml` (path-filtered, edge+publisher only) exist — CI is already
  path-aware/segmented in one place, a good precedent to extend rather than replace.

## 15. Deployment Architecture

`deploy/` holds `Dockerfile.frontend`, `Dockerfile.site`, `nginx.production-light.conf`, a
systemd unit for the live-edge publisher. `apps/api/Dockerfile.api` builds the backend
separately. `docs/` already contains substantial deployment history:
`CLOUDFLARE_EDGE_DEPLOYMENT.md`, `DEPLOY_CLOUDFLARE_ORACLE.md`, `PRODUCTION_RUNBOOK.md`,
`PILOT_RUNBOOK.md`, `ORACLE_MIGRATION_AUDIT_2026-07-15.md`, `PRODUCTION_AUDIT_2026-07-15.md`,
`LIVE_AUDIT_2026-08-24.md`, `LIVE_FIRST_CUTOVER.md`, `FEDERATED_LIVE_RUNBOOK.md`,
`FEDERATED_LIVE_ZERO_COST.md` — **this is a documentation debt problem, not a documentation
absence problem** (see §Documentation debt below). `vercel.json` at repo root plus
`apps/web/vercel.json` suggest Vercel is also a deploy target for the frontend — not fully
reconciled with the Docker/nginx/systemd path in a single canonical doc.

## 16. Technical Debt (cross-cutting)

- **Documentation sprawl**: 10+ dated audit/runbook docs already in `docs/` (several with
  literal dates in the filename: `DOMAIN_FTP_AUDIT_2026-07-15.md`,
  `ORACLE_MIGRATION_AUDIT_2026-07-15.md`, `PRODUCTION_AUDIT_2026-07-15.md`,
  `RESEARCH_AUDIT_2026-07-15.md`, `LIVE_AUDIT_2026-08-24.md`). Adding
  `docs/ARCHITECTURE.md` etc. per roadmap Phase 11 must explicitly supersede/link these, not
  add an eleventh parallel doc — **P3**, but real: a reviewer opening `docs/` today sees audit
  fatigue, which undercuts "senior engineering level" more than any single code issue.
- **`core/intel/store.py` (924 LOC)** and **`core/intel/twikit_monitor.py` (1065 LOC)** are
  the two largest backend modules and the least tested (§13) — highest-value Phase 3/7 targets
  after the frontend shell.
- **Three independent enforcement points for the public/private boundary** (§2) — the
  single highest-leverage Phase 4 target: collapsing to one canonical policy function/type
  would remove an entire class of future "public leaked private data" bugs, not just tidy code.

## 17. Large Files / God Modules

| file | LOC | note |
|---|---|---|
| `apps/web/src/main.jsx` | 3376 | app shell + routing + most data/realtime logic |
| `apps/web/src/styles.css` | 3218 | monolithic stylesheet, no CSS modules/scoping seen |
| `apps/web/src/components/PlayCesium.jsx` | 1230 | map/scene logic entangled with UI |
| `apps/api/core/intel/twikit_monitor.py` | 1065 | unofficial scraper, largest backend file |
| `apps/web/src/components/IntelDashboard.jsx` | 964 | dashboard UI + data shaping combined |
| `apps/api/core/intel/store.py` | 924 | in-memory store + DB sync + business rules |
| `apps/api/core/drift/opendrift_pool.py` | 912 | untested at unit level (§13) |
| `apps/api/core/api/routes/live.py` | 763 | route + public-projection policy combined |
| `apps/api/core/api/routes/intel.py` | 633 | route + domain logic combined, untested (§13) |
| `apps/api/core/live_edge_publisher.py` | 523 | |

## 18. Duplicated Responsibilities

- Public/private policy logic implemented independently three times (§2, §8) — Python
  (`routes/live.py`), Python (`intel/public_geometry.py`, not fully read), JS
  (`apps/edge/src/live.js`).
- HMAC verification implemented independently in Python (ingestion channels) and JS
  (`live.js`) with no shared contract test (§10).
- `docs/contracts/*.schema.json` (5 JSON Schema files) exist and are a good sign of intent
  toward canonical contracts, but it's not verified in this pass whether both the Python and
  JS sides actually validate against them at runtime or only informally follow them — Phase 4
  follow-up question.

## 19. Risky Implicit Contracts

- Route exposure ("is this path public?") is decided by literal path-string membership tests
  in one middleware function (`main.py:126-144`) — adding a new route without updating this
  function silently defaults to requiring auth for non-GET or falls through unexamined for GET
  paths not matching any `startswith` branch. Worth an explicit test enumerating all routers'
  paths against the middleware's rules (Phase 5/7 candidate).
- `JOB_EXECUTION_MODE` and `INTEL_MONITORS_ENABLED` together select one of at least 3 process
  topologies (single-process inline, single-process queue, split API+worker) — undocumented
  outside code comments (§6).
- `source_policy` string values (`"official_api"`, `"unofficial"`, `"nitter"`, `"scrape"`,
  `"twscrape"`, etc.) are the load-bearing mechanism for the public/private and
  trust/no-trust decision across the whole intel pipeline, but are plain strings, not an enum
  or shared type — a typo in a new integration silently fails open or closed depending on
  which allow-list it's compared against (§9, §18).

## 20. Concurrency Risks

- `core/intel/store.py` is an in-process singleton mutated from multiple background
  threads/tasks (sensors, monitors, DB sync loop) — not verified in this pass whether it uses
  locks/async-safety; flagged for Phase 3/5 deep read, not confirmed as a bug here.
- Edge `LiveRoom` Durable Object: Cloudflare guarantees single-threaded execution per DO
  instance, so the JS side itself is not a concurrency risk internally — but the *publisher*
  side (`live_edge_publisher.py`) pushing from a multi-worker Python deployment could race on
  `previous_hash`/version-replacement semantics across rapid successive updates to the same
  incident; no test found exercising rapid-fire updates to one `incident_id`.
- `_start_intel_sync_loop` (`main.py:90-104`) is a bare daemon thread with a fixed 30s sleep
  and silent `except Exception: logger.debug(...)` swallow — a failure here degrades silently
  to stale intel data with no metric/alert (§12 gap, §8 gap combined) — **P1**.

## 21. Failure Recovery

- `bootstrap.reset_stale_computing_jobs()` on startup (non-queue mode) — good sign of
  recovery-awareness.
- `intel_store.reset_computing_drifts()` on startup — same.
- OpenDrift prewarm failure is caught and logged, not fatal (`main.py:64-70`) — correct
  degrade-not-crash behavior.
- Edge worker: no explicit retry/backoff visible for the optional Nostr bridge fan-out beyond
  `.catch(() => undefined)` (`live.js:243`) — intentional best-effort, but undocumented as such
  anywhere outside the code.

## 22. Dependency Risks

- `apps/api/pyproject.toml`: `opendrift>=1.14.9`, `copernicusmarine>=2.3.0`, `xarray` — heavy
  scientific stack, unpinned upper bounds (all `>=`) — reasonable for a research tool, but
  combined with §14's "no dependency security scanning" is the concrete P0/P1 gap the roadmap's
  Phase 6 names explicitly.
- `twifork>=2.3.5` (a fork of a Twitter library) plus `twikit_monitor.py`'s cookie-session
  scraping approach (§9) is inherently fragile to upstream X changes — already acknowledged in
  code comments (`config.py:175-181`), not a hidden risk, just an accepted one worth stating in
  `docs/SECURITY_MODEL.md`.
- `missile-tid` dependency pulled directly from a GitHub URL
  (`pyproject.toml:41`, optional `tid` extra) — no pinned commit hash, floats with the
  upstream default branch — supply-chain risk if that repo is ever compromised; low blast
  radius since it's an optional extra, but worth pinning to a commit SHA.

## 23. Configuration Complexity

`apps/api/core/config.py` is a single 234-line flat `BaseSettings` class covering runtime,
auth, webhooks, object storage, jobs, 6+ sensor subsystems (infrasound/seismic/hydro/SDR/ADSB/
TID), ocean/weather, AIS, intel/twikit, TimeZero — exactly the "one enormous configuration
class becoming the global domain model" the roadmap's Phase 9 warns about. It is well-commented
(several fields have multi-line rationale comments — a real strength, see §Strengths) but has
no internal grouping (no nested settings models per subsystem). `validate_production_security()`
is the only cross-field validation present; combinations like "TID_ENABLED=true but the `tid`
extra isn't installed" aren't validated.

## 24. Public/Private Data Boundaries

Covered extensively in §2, §8, §18. Summary: the *intent* is well-documented in code comments
(the team clearly understands and cares about this boundary — e.g. `routes/live.py:75-92`'s
comments about explicit-private-always-wins semantics), but the *enforcement* is triplicated
across two languages and three modules with no shared contract test. This is the single
highest-value correctness target in the whole repository for a Phase 4+5 PR.

---

## Strengths (do not disturb without reason)

1. `validate_production_security()` (`security.py:118-133`) — real fail-safe config gate.
2. `apps/edge/src/live.js` — small, focused, already has HMAC + timing-safe compare + TTL +
   idempotent ingest + tested (`live.test.js`). Best-built module in the repo.
3. `apps/web/src/simulation/` — the one frontend area already organized close to the target
   architecture (`contracts.js`, `driftEngine.js`, `sceneAdapter.js`, `workerClient.js`, tests).
4. Config comments throughout `config.py` explain *why*, not just *what* — genuine engineering
   discipline, worth preserving as a pattern when the class is eventually split.
5. CI already exists and is fast, parallelized, path-filtered in one workflow — a working
   foundation to extend, not rebuild.
6. `.env.example` is clean — no committed secrets found.

## Notes / Assumptions

- This audit samples large/high-signal files rather than reading all 296 tracked files;
  claims about files not explicitly cited above (e.g. `core/intel/public_geometry.py`,
  `core/probability/*`, `core/forensic/*`) are deliberately not made — flagged as "not read in
  this pass" rather than guessed.
- LOC counts are `wc -l` (physical lines, including blanks/comments), used only as a debt
  signal, not a quality judgment.
- No production runtime was inspected (no deployed environment access in this session) — all
  findings are static-code-only, consistent with Phase 0's "do not modify implementation"
  constraint.

---

## Executive Assessment

SeaCommons is a real, working system with above-average engineering discipline for its stage —
explicit fail-safe production config, a well-built realtime edge module, and code comments that
show the team understands its own hardest problem (public/private data boundaries) even where
the enforcement isn't yet unified. The main gap is not competence, it's **consolidation**: the
same correctness-critical decision (what may become public) is implemented three times, the
same growth pattern (one file absorbs a whole feature) repeats in both frontend and backend,
and CI enforces less than the repo already has tooling installed for (ruff/mypy present, unused).
None of this requires new technology — it requires extracting what's already implicit into one
place per decision, which is exactly what the roadmap's phased PR plan targets.

## Top P0/P1 Risks

1. **P0 (process, not code)** — no dependency security scanning (no `pip-audit`, `npm audit`,
   CodeQL, or Dependabot) despite a heavy, fast-moving scientific/scraping dependency stack. §14.
2. **P1** — public/private data-boundary enforcement triplicated across
   `routes/live.py`, `intel/public_geometry.py`, `apps/edge/src/live.js` with no shared
   contract test. §2, §8, §18, §24.
3. **P1** — realtime invariants named in roadmap Phase 5 (duplicate delivery, out-of-order
   events, restart recovery of `head_hash`) are implemented but not asserted by tests. §8.
4. **P1** — `_start_intel_sync_loop` silently swallows sync failures with no metric —
   split-deployment intel can go stale with no operator signal. §12, §20.
5. **P1** — `core/intel/store.py` concurrency model (multi-threaded mutation of one in-process
   singleton) not verified safe in this pass — needs a focused read before any refactor touches it. §20.

## Top Maintainability Problems

1. `apps/web/src/main.jsx` (3376 LOC) — app shell, routing, data, realtime all fused. §4, §17.
2. `apps/web/src/styles.css` (3218 LOC) — monolithic, unscoped. §17.
3. `core/intel/twikit_monitor.py` (1065) and `core/intel/store.py` (924) — largest, least
   tested backend modules. §13, §16.
4. Route modules mix parsing/authz/domain logic/serialization (`routes/live.py` 763,
   `routes/intel.py` 633). §3, §17.
5. `npm run lint` performs no actual linting (it's `tsc --noEmit`); ruff/mypy installed but
   never run in CI. §13, §14.
6. Documentation sprawl — 10+ dated audit docs with no superseding index. §16.

## Suggested Target Architecture

Adopt the roadmap's proposed shapes as-is — they match what already exists in embryonic form
(`apps/web/src/simulation/` for frontend, `core/domain/` for backend) — rather than designing a
new one. Concretely: frontend `features/{live,intel,drift,vessels,cases,connectors,simulation}`
+ `services/{api,realtime,storage}` + `domain/`; backend thin routes →
`core/services/`/`core/domain/` → existing subsystem packages as the repository/integration
layer. No new frameworks, no state library, no microservices — consistent with the roadmap's
explicit prohibitions and with what this audit found (the codebase doesn't need more
technology, it needs the existing technology's responsibilities separated).

## Ordered PR Roadmap (adjusted from roadmap's default sequence)

1. **PR 1 — Engineering baseline + CI gate completion.** Wire ruff/mypy (already installed)
   into `ci.yml`; add `pip-audit` and `npm audit --audit-level=high` as CI steps; add
   `dependabot.yml`. No app code changes. Lowest risk, highest signal for "maintained at
   senior level."
2. **PR 2 — Public/private boundary consolidation (backend).** Extract the three independent
   policy checks (§2/§18/§24) into one canonical function/module in `core/domain/`, called
   from `routes/live.py` and documented for the edge side to match in PR 3.
3. **PR 3 — Realtime invariant tests.** Add tests asserting the Phase 5 invariants (resolved
   incidents can't return to active, duplicate delivery is idempotent, restart recovers
   `head_hash`) against both `apps/edge/src/live.js` and the publisher.
4. **PR 4 — Frontend domain contracts / TypeScript foundation.** Add `apps/web/src/types/`
   with the roadmap's listed interfaces (`LiveIncident`, `IntelEvent`, `DriftResult`, etc.),
   enable `"strict": true` for new files only via incremental `tsconfig` scoping.
5. **PR 5 — Extract realtime/live frontend logic out of `main.jsx`** into
   `features/live/` + `services/realtime/`, following the `simulation/` module's existing
   pattern.
6. **PR 6 — Extract map/Cesium responsibilities** from `PlayCesium.jsx` into
   `components/map/` + `features/drift/` or `features/vessels/` as appropriate once actually
   read in depth.
7. **PR 7 — Backend route decomposition** for `routes/live.py` and `routes/intel.py`
   (the two largest, least-tested route modules) into thin route + `core/services/`.
8. **PR 8 — Observability for split-deployment/background sync.** Add a metric/log-level
   escalation for `_start_intel_sync_loop` failures and worker/source health gauges (§12,§20).
9. **PR 9 — Documentation consolidation.** Add `docs/ARCHITECTURE.md`, `docs/DATA_FLOW.md`,
   `docs/SECURITY_MODEL.md`, `docs/REALTIME_ARCHITECTURE.md`; explicitly supersede/link the
   10+ existing dated audit docs rather than adding an unlinked eleventh.
10. **PR 10 — Repository polish.** CODEOWNERS, issue/PR templates, CHANGELOG, ADRs — once the
    substance above is in place.

## Roadmap progress log

Implementation status as of 2026-08-26. “Complete” means implemented and
verified on the named local branch/commit; it does not claim remote merge or
production deployment.

| Roadmap item | Status | Implementation |
|---|---|---|
| PR 1 — Engineering baseline + CI gates | Complete | `427e674` |
| PR 2 — Public/private boundary consolidation | Complete | `8ac1e0e` |
| PR 3 — Realtime invariant tests | Complete | `ad3e4d2` |
| PR 4 — Frontend domain contracts | Complete | `e213eb9` |
| PR 5 — Frontend realtime extraction | Complete | `73dc8ab` |
| PR 6 — Cesium responsibility extraction | Complete | `712ace5` |
| PR 7 — Backend route decomposition | Complete | `c0ac398` |
| Canonical Live contracts (cross-cutting follow-up) | Complete | `22a87fc` |
| PR 8 — Split-runtime observability | Complete | `7297c68` |
| PR 9 — Documentation consolidation | Complete | `docs/consolidate-architecture` |
| PR 10 — Repository polish | Complete | `chore/repository-polish` |

The PR branches are intentionally small review units but currently form a
partially stacked local history. Before remote merge, preserve their dependency
order or rebase each branch onto the merged predecessor.

## Exact Files Affected by PR #1

- `.github/workflows/ci.yml` (add ruff/mypy/pip-audit steps to the `api` job; add
  `npm audit` to the `web` and `edge` jobs)
- `.github/dependabot.yml` (new file)
- No files under `apps/api/core/`, `apps/web/src/`, or `apps/edge/src/` change.
- Possibly `apps/api/pyproject.toml` if ruff/mypy config needs minor adjustment to pass
  cleanly on first run (verify, don't assume — first run may surface pre-existing lint/type
  issues that need triage, not blanket suppression).

## Acceptance Criteria for PR #1

1. `ci.yml`'s `api` job runs `ruff check .` and `mypy core` (or scoped equivalent) as
   additional steps; both pass or documented `# noqa`/`# type: ignore` are added only for
   genuine, individually-justified cases — no blanket ignore file.
2. `ci.yml`'s `api` job runs `pip-audit` (or equivalent); job fails on high/critical
   vulnerabilities with no known-safe exceptions, or documented suppressions if a fix isn't
   yet available upstream.
3. `web` and `edge` jobs run `npm audit --audit-level=high` (or equivalent); same failure
   policy.
4. `.github/dependabot.yml` configured for at least `pip` (apps/api), `npm` (apps/web,
   apps/edge), and `github-actions` ecosystems, weekly cadence.
5. No existing test regresses; `pytest -q`, `npm run test:simulation`, `npm test` (edge) all
   still green.
6. No application behavior changes — this PR touches only CI/CD configuration and dependency
   manifests.
7. PR description states current ruff/mypy/audit findings count (even if some are deferred to
   follow-up PRs) so the baseline is visible, not hidden.
