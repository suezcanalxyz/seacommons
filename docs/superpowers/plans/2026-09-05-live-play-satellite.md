# Live / Play / Satellite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate 24h operational Live from historical Play, repair Drift ownership, replace public Play simulation with a timeline map, and add a free provider-agnostic satellite observation pipeline.

**Architecture:** Canonical incident status is separated from public surface. Live projects only current operational incidents and current drift pointers; Play reconstructs persisted observations/products by time. Satellite observations are persisted as evidence and can be queried reverse/nearest/forward.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, APScheduler, React 19, MapLibre, Node test runner, Copernicus STAC, NASA GIBS/VIIRS.

**Spec:** `docs/superpowers/specs/2026-09-05-live-play-satellite-design.md`

## Global Constraints

- Live rolling operational window is exactly 24 hours.
- `resolved` never remains visible in Live.
- `archived` is not exposed as a public incident outcome.
- Drift authority remains `HumanitarianIncident.current_drift_id`.
- Public Play uses MapLibre; no Cesium/Unreal public renderer.
- Satellite evidence must include acquisition time and provenance.
- Satellite vessel association is candidate evidence, not identity proof.
- Free sources must work without credentials; GFW is optional when configured.

---
### Task 1: Separate incident status from Live retirement

**Files:**
- Modify: `apps/api/core/domain/live_contracts.py`
- Modify: `apps/api/core/intel/lifecycle.py`
- Modify: `apps/api/core/intel/humanitarian_incident.py`
- Modify: `apps/api/core/db/models.py`
- Create: `apps/api/alembic/versions/0017_incident_status_surface.py`
- Test: `tests/test_humanitarian_incident.py`
- Test: `tests/test_p0_10_live_authority_cutover.py`

**Interfaces:**
- Produces: `IncidentStatus`, `public_incident_status(...)`, persisted `incident_status`.
- Keeps: legacy `lifecycle` readable during migration.

- [ ] Write failing tests: active <24h => active; silent >=24h => outcome_unknown; resolved stays resolved; archived legacy maps to outcome_unknown.
- [ ] Run targeted tests and verify RED for missing `IncidentStatus`/column.
- [ ] Add migration/model field and minimal status mapping.
- [ ] Make incident sync idempotent under concurrent subscriber/backfill writes.
- [ ] Run targeted tests and verify GREEN.
- [ ] Commit `feat(lifecycle): separate incident status from live retirement`.
### Task 2: Enforce 24h Live and terminal-state removal

**Files:**
- Modify: `apps/api/core/live/feed.py`
- Modify: `apps/api/core/live_edge_publisher.py`
- Modify: `apps/api/core/intel/lifecycle.py`
- Modify: `apps/api/core/scheduler.py`
- Test: `tests/test_live_feed.py`
- Test: `tests/test_live_edge_publisher.py`

**Interfaces:**
- Consumes: `IncidentStatus`, `resolve_public_incident_state()`.
- Produces: Live feed containing only operational incidents inside 24h.

- [ ] Write failing tests proving >24h active is absent, canonical resolved is absent, needs_review <24h remains, and edge emits removal.
- [ ] Run targeted tests and verify RED against the current 7-day behavior.
- [ ] Change distress operational window to 24h and filter terminal public status after canonical resolution.
- [ ] Add periodic incident reconciliation job so silent active rows persist `outcome_unknown`/retirement without a new source post.
- [ ] Run VM/edge parity tests and scheduler tests; verify GREEN.
- [ ] Commit `fix(live): make public live a 24 hour operational surface`.
### Task 3: Repair Drift ownership for legacy incidents

**Files:**
- Create: `apps/api/core/intel/backfill_humanitarian_incidents.py`
- Modify: `apps/api/core/intel/backfill_current_drift.py`
- Modify: `apps/api/core/intel/drift_ownership.py`
- Test: `tests/test_backfill_humanitarian_incidents.py`
- Test: `tests/test_backfill_current_drift.py`
- Test: `tests/test_p0_11_drift_authority_cutover.py`

**Interfaces:**
- Produces: dry-run-first `find_candidates()` / `run(apply=False|True)` maintenance commands.
- Preserves: `current_drift_id` as the only operational pointer.

- [ ] Write failing test for a persisted Humanitarian IntelEvent with completed drift but no HumanitarianIncident row.
- [ ] Verify RED: current backfill cannot recover it.
- [ ] Add idempotent incident backfill from durable Humanitarian events, then allow pointer backfill only for open incidents.
- [ ] Add tests that resolved/outcome_unknown incidents never regain operational drift.
- [ ] Run both backfill suites and Drift authority tests; verify GREEN.
- [ ] Commit `fix(drift): repair legacy humanitarian drift ownership`.
### Task 4: Build Play incident timeline API

**Files:**
- Create: `apps/api/core/api/routes/play.py`
- Modify: `apps/api/core/api/main.py`
- Modify: `apps/api/core/db/models.py`
- Test: `tests/test_play_timeline.py`

**Interfaces:**
- Produces: `GET /api/v1/play/incidents` and `GET /api/v1/play/incidents/{incident_id}/timeline`.
- Timeline item shape: `{id, at, type, source, title, geometry, properties}`.

- [ ] Write failing API tests for explicit incident_status, report + transition + drift timeline ordering, and privacy-safe output.
- [ ] Verify RED with route missing.
- [ ] Implement incident index from HumanitarianIncidentDB plus durable events.
- [ ] Implement timeline aggregation for founding report, source updates, state transitions and completed DriftResultDB rows.
- [ ] Keep legacy `/api/v1/live/archives` compatible but route new Play UI to `/api/v1/play/*`.
- [ ] Run route and privacy tests; verify GREEN.
- [ ] Commit `feat(play): expose incident reconstruction timeline`.
### Task 5: Add free SatelliteObservation resolver

**Files:**
- Create: `apps/api/core/intel/satellite_observation.py`
- Create: `apps/api/core/intel/satellite_resolver.py`
- Modify: `apps/api/core/db/models.py`
- Create: `apps/api/alembic/versions/0018_satellite_observations.py`
- Modify: `apps/api/core/api/routes/play.py`
- Test: `tests/test_satellite_resolver.py`
- Test: `tests/test_play_timeline.py`

**Interfaces:**
- Produces: `SatelliteObservation`, `resolve_for_incident(..., direction)` and persisted timeline items.
- Free providers: CDSE STAC (`sentinel-1-grd`, `sentinel-2-l2a`, Sentinel-3 NRT collections) plus dated NASA GIBS VIIRS layer metadata.

- [ ] Write failing pure tests for reverse/nearest/forward temporal classification and VIIRS dated tile template metadata.
- [ ] Write failing client test proving Copernicus search uses bbox + datetime and returns normalized observations.
- [ ] Verify RED for missing resolver.
- [ ] Implement provider-agnostic normalization and credential-free Copernicus STAC discovery.
- [ ] Add VIIRS NOAA-20/NOAA-21/SNPP dated GIBS observations as daily optical context.
- [ ] Persist observations idempotently and expose them in Play timeline; do not auto-identify vessels.
- [ ] Run satellite/timeline tests; verify GREEN.
- [ ] Commit `feat(satellite): add free temporal observation resolver`.
### Task 6: Replace public Play simulation UI and align Live panels

**Files:**
- Create: `apps/web/src/features/play/timeline.js`
- Create: `apps/web/src/features/play/PlayTimeline.jsx`
- Modify: `apps/web/src/main.jsx`
- Modify: `apps/web/src/components/ConePanel.jsx`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/package.json`
- Test: `apps/web/src/features/play/timeline.test.js`
- Test: `apps/web/src/features/live/*.test.js`

**Interfaces:**
- Consumes: `/api/v1/play/incidents`, `/timeline`, `/api/v1/live/drifts`.
- Produces: MapLibre Play timeline and one scrollable Live detail-panel pattern.

- [ ] Write failing JS tests for timeline ordering, current-frame selection, satellite raster selection and incident-status labels.
- [ ] Verify RED for missing Play timeline module.
- [ ] Route `play.seacommons.org` to PlayTimeline instead of PlayCesium/Unreal controls.
- [ ] Keep Live map operational and remove archived-feed language; guarantee panel body vertical scrolling on desktop/mobile.
- [ ] Remove Cesium from public Play dependency/import path; retain simulation code only if another non-public route still imports it.
- [ ] Run lint, typecheck, live/map/play tests and `npm run build:unified`; verify GREEN.
- [ ] Commit `feat(web): turn play into temporal osint timeline`.
### Task 7: Full verification and controlled rollout

**Files:**
- Modify: `docs/updates.md` with the shipped contract and operator backfill order.

**Interfaces:**
- Produces: merge-ready branch and explicit production migration/backfill procedure.

- [ ] Run full backend pytest and migration upgrade on a disposable database.
- [ ] Run full frontend lint, typecheck, tests and unified production build.
- [ ] Run `git diff --check` and verify migration revision IDs <=32 characters.
- [ ] Push branch, open PR, wait for Full CI and CodeQL, review diff and unresolved threads.
- [ ] Merge only after green gates.
- [ ] Production order: backup -> Alembic upgrade -> incident backfill dry-run/apply -> drift-pointer backfill dry-run/apply -> coordinated service restart -> Live/Play smoke.
- [ ] Verify Live has no >24h/terminal incidents, Play retains them with status, drift count is coherent, and satellite timeline endpoint degrades safely if external providers are unavailable.
- [ ] Deploy frontend after backend smoke, then verify `live.seacommons.org` and `play.seacommons.org` asset hashes match the merged build.

## Plan self-review

- Spec coverage: lifecycle/surface, Drift, Play timeline, satellite resolver, UI and rollout are each assigned to a task.
- No implementation task bypasses `current_drift_id` or turns satellite candidates into confirmed vessel identity.
- Migration order is linear: 0017 incident status, then 0018 satellite observations.
- Public Play has a dedicated API contract and no dependency on the legacy archive endpoint.
- Live/Play privacy boundaries stay on public projections, not raw source payloads.