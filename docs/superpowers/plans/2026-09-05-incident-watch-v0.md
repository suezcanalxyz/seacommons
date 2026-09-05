# IncidentWatch v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add restart-safe, bounded Humanitarian incident follow-up watches that can collect new evidence through existing adapters without directly mutating canonical incident truth.

**Architecture:** Persist one `IncidentWatchDB` row per canonical `HumanitarianIncidentDB`, derive a deterministic sparse profile from already persisted evidence, and schedule due watches with an optimistic lease. v0 exposes a narrow adapter protocol and integrates only the already-existing official X monitor for bounded `conversation_id:<tweet_id>` follow-up when configured; all discovered posts still enter through that monitor's existing SourceObservation + IntelEvent paths. The change is backend-only; Live/Play vessel UI remains untouched and is verified by its existing frontend suites.

**Tech Stack:** Python 3.12, SQLAlchemy, Alembic, FastAPI, APScheduler, pytest, ruff; React/Vite frontend regression verification only.

**Spec:** `docs/superpowers/specs/2026-09-05-incident-watch-v0-design.md`

## Global Constraints

- `SourceObservation` remains the immutable acquisition boundary for every newly discovered source item.
- `IncidentWatch` never directly mutates Humanitarian lifecycle, assessment, correlation, Drift, public Live features, or vessel state.
- Current compatibility rule: `incident_status=outcome_unknown` overrides legacy `lifecycle=archived` for watch scheduling, so unresolved silent incidents keep bounded follow-up.
- No new crawler, paid provider, PostGIS dependency, LLM state mutation, production migration, deploy, service restart, or production database mutation.
- Humanitarian public output must not gain MMSI, IMO, callsign, commercial tracker links, exact watch profiles, or private watch metadata.
- UI navi/vessel is a release gate: no changes to vessel marker shape/type, SAR fleet rendering, Live/Play routing, or vessel dossier behavior.
- Alembic revision identifier must be <= 32 characters and revise `0018_satellite_observations`.

---

### Task 1: Persist IncidentWatch and prove migration parity

**Files:**
- Modify: `apps/api/core/db/models.py`
- Create: `apps/api/core/db/migrations/versions/0019_incident_watch.py`
- Modify: `tests/test_alembic_migrations.py`
- Create: `tests/test_incident_watch.py`

**Interfaces:**
- Produces: `IncidentWatchDB` with `incident_id` unique, operational schedule state, error counters, fingerprint and lease fields.

- [ ] **Step 1: Write failing persistence tests**

Add tests asserting model metadata contains `incident_watches`, `incident_id` is unique, and the migration head matches model metadata after `alembic upgrade head`.

```python
def test_incident_watch_model_has_unique_incident_and_schedule_index():
    from sqlalchemy import inspect
    from core.db.models import IncidentWatchDB
    table = IncidentWatchDB.__table__
    assert table.name == "incident_watches"
    assert any(c.name == "incident_id" for c in table.columns)
    assert any("incident_id" in [col.name for col in constraint.columns]
               for constraint in table.constraints if hasattr(constraint, "columns"))
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=apps/api .venv/bin/python -m pytest tests/test_incident_watch.py tests/test_alembic_migrations.py -q`
Expected: FAIL because `IncidentWatchDB`/migration do not exist.

- [ ] **Step 3: Add minimal model and migration**

Create fields:
`watch_id`, `incident_id`, `status`, `priority`, `lifecycle_snapshot`, `profile_json`, `profile_version`, `next_run_at`, `last_run_at`, `last_success_at`, `last_error_at`, `last_error_class`, `consecutive_errors`, `run_count`, `query_fingerprint`, `lease_owner`, `lease_until`, `created_at`, `updated_at`, `expires_at`.

Use unique constraint on `incident_id` and index `(status, next_run_at, priority)`.

- [ ] **Step 4: Run GREEN**

Run the same targeted pytest command and confirm 0 failures.

- [ ] **Step 5: Commit**

`git commit -am "feat: persist incident watches"` plus the new files.

### Task 2: Deterministic watch policy, sparse profile, and idempotent sync

**Files:**
- Create: `apps/api/core/intel/incident_watch.py`
- Modify: `apps/api/core/intel/humanitarian_incident.py`
- Modify: `tests/test_incident_watch.py`
- Modify: `tests/test_humanitarian_incident.py`

**Interfaces:**
- Produces: `WatchPolicy`, `build_watch_profile(db, incident)`, `sync_watch_for_incident(incident_id, now=None)`, `get_watch(incident_id)`.

- [ ] **Step 1: Write failing policy/profile/sync tests**

Cover active -> highest/15m, needs_review -> high/30m, outcome_unknown + archived compatibility -> medium/2h, old resolved -> expiry, deterministic profile, omitted unknown fields, and one-watch-per-incident idempotency.

```python
def test_outcome_unknown_legacy_archived_keeps_followup():
    policy = policy_for_state(
        incident_status="outcome_unknown", lifecycle="archived",
        resolved_at=None, now=NOW,
    )
    assert policy.status == "active"
    assert policy.priority == "medium"
    assert policy.cadence == timedelta(hours=2)
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=apps/api .venv/bin/python -m pytest tests/test_incident_watch.py tests/test_humanitarian_incident.py -q`
Expected: FAIL because policy/profile/sync APIs are missing.

- [ ] **Step 3: Implement minimal deterministic policy/profile/sync**

Profile sources are canonical incident + primary `IntelEventDB` only in v0. Extract only explicit metadata such as `tweet_id`, explicit coordinates/uncertainty, source name, case type, and already-associated observation ids. Do not NLP-infer route, vessel identity, people count or language.

Call `sync_watch_for_incident()` best-effort after `sync_incident_for_event()` succeeds; watch failures must not break ingestion.

- [ ] **Step 4: Run GREEN**

Run targeted tests and ensure both suites pass.

- [ ] **Step 5: Commit**

`git commit -am "feat: sync bounded incident watch profiles"`

### Task 3: Due-watch leasing and bounded execution contract

**Files:**
- Modify: `apps/api/core/intel/incident_watch.py`
- Modify: `tests/test_incident_watch.py`

**Interfaces:**
- Produces: `claim_due_watches(now, limit, lease_owner, lease_seconds)`, `WatchQuery`, `WatchResult`, `run_claimed_watch(watch_id, adapters=None, now=None)`.

- [ ] **Step 1: Write failing lease/execution tests**

Prove only due watches are claimed, priority order is deterministic, an unexpired lease prevents duplicate execution, same query fingerprint is not rerun inside the cadence window, three failures degrade/back off, and adapter failure does not change `HumanitarianIncidentDB`.

- [ ] **Step 2: Run RED**

Run targeted IncidentWatch tests; expect missing APIs.

- [ ] **Step 3: Implement optimistic lease and adapter protocol**

Use a conditional SQL UPDATE against candidate rows so SQLite tests and PostgreSQL both avoid double-claim. Limit one watch execution at a time in v0; max adapters per run = 3 and max accepted observations = 25.

- [ ] **Step 4: Run GREEN**

Run targeted tests and confirm 0 failures.

- [ ] **Step 5: Commit**

`git commit -am "feat: lease and execute incident watches"`

### Task 4: Existing official X adapter as first bounded follow-up source

**Files:**
- Modify: `apps/api/core/intel/twitter_monitor.py`
- Modify: `apps/api/core/intel/incident_watch.py`
- Modify: `tests/test_incident_watch.py`
- Modify/Create: `tests/test_twitter_monitor.py` if existing coverage location supports it.

**Interfaces:**
- Produces: `TwitterMonitor.watch_conversation(tweet_id, *, watch_id, incident_id, budget=20) -> WatchResult`.

- [ ] **Step 1: Write failing adapter tests**

Use a fake `_fetch` result to prove query is exactly `conversation_id:<tweet_id> -is:retweet`, result is bounded to <=20, every accepted post passes through `_record_source_observation()`/existing `_ingest()`, and provenance contains `collection_trigger=incident_watch`, `watch_id`, `candidate_incident_id` without forcing correlation.

- [ ] **Step 2: Run RED**

Run the adapter + IncidentWatch tests; expect missing method/provenance support.

- [ ] **Step 3: Implement minimal adapter**

Extend `_record_source_observation()` and `_ingest()` with optional watch provenance. `IncidentWatch` declares the official X adapter eligible only when the existing monitor is configured and the profile has explicit tweet ids. No credentials or endpoint changes.

- [ ] **Step 4: Run GREEN**

Run targeted tests and ensure idempotent replay produces no duplicate SourceObservation.

- [ ] **Step 5: Commit**

`git commit -am "feat: follow incident threads via existing x adapter"`

### Task 5: Scheduler and operator audit surface

**Files:**
- Modify: `apps/api/core/scheduler.py`
- Modify: `apps/api/core/api/routes/audit.py`
- Modify: `tests/test_scheduler.py`
- Modify: `tests/test_incident_watch.py`

**Interfaces:**
- Produces: scheduler job `incident_watch`, audit endpoint `GET /api/v1/audit/incident-watches`.

- [ ] **Step 1: Write failing scheduler/audit tests**

Assert scheduler registers one max-instance watch job, job processes a bounded due batch, endpoint returns operational metadata only, and response excludes `profile_json` and raw source text.

- [ ] **Step 2: Run RED**

Run scheduler + IncidentWatch tests; expect missing job/route.

- [ ] **Step 3: Implement minimal scheduler and audit endpoint**

Run scheduler every 5 minutes with `max_instances=1`; due selection still obeys per-watch `next_run_at`. Audit response includes watch id, incident id, state/priority, lifecycle snapshot, timestamps, error/run counts, profile version and eligible adapter names only.

- [ ] **Step 4: Run GREEN**

Run targeted backend tests.

- [ ] **Step 5: Commit**

`git commit -am "feat: schedule and audit incident watches"`

### Task 6: Full verification and vessel/Live/Play regression gate

**Files:**
- No frontend production files should change.
- Update docs only if verification finds a documented mismatch.

**Interfaces:**
- Consumes all prior tasks; produces release evidence only.

- [ ] **Step 1: Verify changed-file boundary**

Run: `git diff --name-only origin/main...HEAD`
Expected: no files under `apps/web/src/` changed.

- [ ] **Step 2: Full backend verification**

Run:
`PYTHONPATH=apps/api .venv/bin/python -m pytest -q`
`PYTHONPATH=apps/api .venv/bin/ruff check apps/api tests`

Expected: 0 failures / 0 ruff errors.

- [ ] **Step 3: Explicit UI navi/vessel verification**

From `apps/web` run:
`npm run test:live`
`npm run test:play`
`npm run test:map`
`npm run lint`
`npm run build:unified`

Additionally run focused vessel tests:
`node --test src/features/live/vesselMarker.test.js src/features/live/vesselType.test.js src/features/live/sarFleet.test.js src/features/live/observedTrack.test.js`

Expected: all green; vessel triangles/types/SAR fleet/observed tracks unchanged.

- [ ] **Step 4: Migration roundtrip verification**

Run focused Alembic tests and ensure `upgrade head` schema matches model metadata.

- [ ] **Step 5: Independent diff review**

Review for privacy, accidental incident mutation, query loops, lease races, migration safety, and any vessel/UI coupling. Fix findings with a failing regression test first.

- [ ] **Step 6: Open implementation PR, but do not merge/deploy automatically**

PR must state exact test counts/commands from fresh runs and explicitly note that production migration/deploy remains separate.
