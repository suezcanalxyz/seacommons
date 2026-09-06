# Vessel Context + Behavioural Baseline v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic vessel context, versioned behavioural baselines, and explainable behaviour assessments without creating vessel reputation scores or direct allegations.

**Architecture:** Reuse VesselSubject, VesselRegistry and VesselTrackDB as canonical inputs. Persist only versioned baseline products in PostgreSQL; compute VesselContext and BehaviourAssessment as deterministic projections. Detector integration may attach behaviour context but may not open Cases solely because behaviour is unusual.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL/SQLite test DB, pytest.

**Spec:** `docs/superpowers/specs/2026-09-06-vessel-context-behavioural-baseline-v1-design.md`

## Global Constraints
- No vessel risk/reputation score, whitelist, blacklist, or intent inference.
- Top-level assessment states are exactly `expected`, `unusual`, `insufficient_history`.
- Baselines are versioned analytical products with evidence fingerprints.
- Humanitarian privacy and OSINT Evidence Pipeline v1 lineage rules remain authoritative.
- YOUR WISDOM appears only in synthetic regression fixtures/tests, never production hard-code.
- No public UI changes in this packet.

---

### Task 1: VesselContext projection

**Files:**
- Create: `apps/api/core/mda/vessel_context.py`
- Modify: `apps/api/core/api/routes/mda.py`
- Test: `tests/test_vessel_context.py`

**Interfaces:**
- Produces: `build_vessel_context(mmsi: str, *, hours: float = 24*30) -> dict`
- Uses: registry cache, `track_store.track`, `subject_id_for`, existing port-call derivation.
- [ ] **Step 1: Write failing context tests** asserting subject identity, static facts, recent port calls, sample/history metadata, and derived labels remain explicitly `derived`.
- [ ] **Step 2: Run RED** with `PYTHONPATH=apps/api .../.venv/bin/python -m pytest -q tests/test_vessel_context.py` and confirm missing module/API failure.
- [ ] **Step 3: Implement minimal projection** with no persistence and no external network calls.
- [ ] **Step 4: Run GREEN** for `tests/test_vessel_context.py` plus existing MDA vessel dossier tests.
- [ ] **Step 5: Commit** `feat: add deterministic vessel context projection`.

### Task 2: Behavioural baseline persistence and builder

**Files:**
- Create: `apps/api/core/mda/behavioural_baseline.py`
- Modify: `apps/api/core/db/models.py`
- Create: `apps/api/alembic/versions/0020_vessel_baselines.py`
- Test: `tests/test_behavioural_baseline.py`, `tests/test_alembic_migrations.py`

**Interfaces:**
- Produces: `build_baseline(mmsi: str, *, window_days: int = 30) -> BehaviouralBaseline | None`
- Produces: `persist_baseline(baseline)`, `latest_baseline(mmsi)`.
- Baseline contains sample_count, time window, route cells/corridor, speed quantiles, recurrent ports/pairs, gap quantiles, evidence_fingerprint, method_version.

- [ ] **Step 1: Write migration/model RED tests** for table shape and append/version semantics.
- [ ] **Step 2: Write builder RED tests** using synthetic tracks for deterministic fingerprint and robust quantiles.
- [ ] **Step 3: Run RED** and verify missing table/module failures.
- [ ] **Step 4: Implement migration/model and minimal deterministic builder** using only historical VesselTrackDB data.
- [ ] **Step 5: Run GREEN**, including Alembic upgrade/downgrade/upgrade tests.
- [ ] **Step 6: Commit** `feat: add versioned vessel behavioural baselines`.

### Task 3: BehaviourAssessment
**Files:**
- Create: `apps/api/core/mda/behaviour_assessment.py`
- Test: `tests/test_behaviour_assessment.py`

**Interfaces:**
- Produces: `assess_behaviour(current_track: list[dict], baseline: BehaviouralBaseline | None) -> BehaviourAssessment`.
- Reason codes: `ROUTE_DEVIATION`, `UNUSUAL_SPEED_PROFILE`, `UNUSUAL_PORT_PAIR`, `UNUSUAL_AIS_SILENCE`, `INSUFFICIENT_HISTORY`.
- Output includes per-dimension evidence, thresholds/percentiles and baseline_id/method_version; no suspicion score.

- [ ] **Step 1: Write RED tests** for insufficient history, expected recurrent service, and contrastive unusual deviation.
- [ ] **Step 2: Run RED** and confirm missing assessment module.
- [ ] **Step 3: Implement minimal explainable assessment** using robust distance/quantile comparisons specified by the spec.
- [ ] **Step 4: Run GREEN** and ensure no intent/allegation vocabulary appears in output.
- [ ] **Step 5: Commit** `feat: add explainable vessel behaviour assessment`.

### Task 4: Operator API and detector context integration

**Files:**
- Modify: `apps/api/core/api/routes/mda.py`
- Modify: `apps/api/core/mda/watch.py`
- Test: `tests/test_mda_behaviour_context.py`, `tests/test_security.py`

**Interfaces:**
- Adds operator GET `/api/v1/mda/vessel/{mmsi}/baseline`.
- Extends operator dossier/context with baseline summary and behaviour assessment.
- AIS-derived observations may receive `behaviour_context` metadata only; unusual status alone must not set `open_case=True` or public publication.

- [ ] **Step 1: Write RED API/security tests** for operator access and privacy-safe public behavior.
- [ ] **Step 2: Write RED detector tests** proving unusual behavior is context only and expected recurrent behavior does not promote a case.
- [ ] **Step 3: Run RED**.
- [ ] **Step 4: Implement bounded integration** with no new scheduler and no public endpoint expansion.
- [ ] **Step 5: Run GREEN** plus fusion/Live privacy regressions.
- [ ] **Step 6: Commit** `feat: attach behavioural context to MDA observations`.

### Task 5: Regression corpus and production gates

**Files:**
- Modify/Create: `tests/fixtures/osint/benign_service_vessels.jsonl`
- Create: `tests/fixtures/osint/behaviour_contrastive.jsonl`
- Modify: `docs/current_work.md`, `prompt.md`

- [ ] **Step 1: Add YOUR WISDOM recurrent-service fixture** and a contrastive route-deviation fixture with synthetic timestamps/geometry.
- [ ] **Step 2: Add RED regression tests** proving no production hard-code and expected vs unusual outcomes differ only from behavior.
- [ ] **Step 3: Implement only generic changes needed by fixtures**.
- [ ] **Step 4: Run focused regression suites** for context/baseline/assessment/fusion/Live/Play/privacy/vessel markers.
- [ ] **Step 5: Run full backend `pytest -q`, Ruff critical gate, canonical mypy, Alembic clean upgrade, pip-audit.**
- [ ] **Step 6: Run web lint/test/build and edge test/Wrangler dry-run/npm audits.**
- [ ] **Step 7: Verify `git diff --check`, no Humanitarian identifier leakage, and no YOUR WISDOM production-code occurrence.**
- [ ] **Step 8: Commit docs/test finalization** `test: harden vessel behavioural baseline regressions`.

### Task 6: PR, CI, merge and controlled rollout

- [ ] **Step 1: Push branch and open PR** against current `main` with exact verification evidence.
- [ ] **Step 2: Require Full CI, CodeQL and lifecycle workflows success** on exact head SHA.
- [ ] **Step 3: Merge exact tested SHA** only after all server-side gates are green.
- [ ] **Step 4: Confirm Vercel production deployment READY** for merge commit.
- [ ] **Step 5: Create PostgreSQL backup, fast-forward production VM, run Alembic `upgrade head` to 0020, restart supervised services, verify `/ready`.
- [ ] **Step 6: Build a bounded production baseline sample** only for sufficiently observed non-Humanitarian vessels; no fleet-wide blind backfill.
- [ ] **Step 7: Smoke operator context/baseline, public Live/Play, and verify zero private behaviour metadata/Humanitarian IDs leak publicly.
- [ ] **Step 8: Audit runtime errors and DB baseline counts; document rollback artifact and final production commit.**

## Completion Criteria
The packet is complete only when deterministic context and baseline behavior are reproducible; expected/unusual/insufficient-history are explainable; unusual behavior alone cannot open a Case; YOUR WISDOM has no hard-coded suppression; Humanitarian privacy and vessel marker contracts pass; CI/CodeQL are green; migration 0020 and production smoke are verified.
