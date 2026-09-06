# Observation → Episode → Hypothesis v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist bounded MaritimeEpisode objects and make new InvestigationHypothesis creation depend on episode-level evidence lineage, behavioural context, and explicit eligibility gates rather than detector count.

**Architecture:** Keep `IntelEvent`/`SourceObservation` as evidence authorities, persist deterministic `MaritimeEpisodeDB` rows as derived analytical objects, and attach every new v1 hypothesis to exactly one episode. Legacy hypotheses remain untouched with `episode_id=NULL`; public publication policy stays unchanged.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, pytest, existing SeaCommons evidence-lineage/behavioural-baseline modules.

**Spec:** `docs/superpowers/specs/2026-09-06-observation-episode-hypothesis-v1-design.md`

## Global Constraints

- Observation is not corroboration; detector multiplicity is not source independence.
- Safety is never a fallback: unknown maritime anomaly types map to `unclassified_episode`.
- BehaviourAssessment is context, never a second independent source.
- Low-specificity AIS patterns cannot create a new v1 hypothesis without independent corroboration.
- High-specificity spoofing may create a `candidate` from one lineage but cannot advance on detector count.
- Legacy hypotheses are never silently rewritten or relinked.
- Humanitarian privacy and existing public hypothesis publication gates remain authoritative.

---
### Task 1: Persisted MaritimeEpisode schema and legacy-safe hypothesis link

**Files:**
- Modify: `apps/api/core/db/models.py`
- Create: `apps/api/core/db/migrations/versions/0021_maritime_episodes.py`
- Test: `tests/test_maritime_episode_schema.py`

**Interfaces:**
- Produces `MaritimeEpisodeDB` with deterministic `episode_id`, subject/family/time bounds, observation/evidence IDs, independence groups, verification status, behaviour context, alternative explanations, fingerprint, method version, status and timestamps.
- Adds nullable/indexed `InvestigationHypothesisDB.episode_id`; NULL is the explicit legacy marker.

- [ ] Write a failing schema test asserting both the new table contract and nullable hypothesis `episode_id`.
- [ ] Run `pytest tests/test_maritime_episode_schema.py -q` and verify RED because the model/migration is absent.
- [ ] Add the SQLAlchemy model and Alembic `0021` migration; do not backfill or update existing hypothesis rows.
- [ ] Run the schema test GREEN, then exercise Alembic `0020 -> 0021 -> 0020 -> 0021` in the test environment.
- [ ] Commit as `feat: add persisted maritime episode schema`.

### Task 2: Deterministic episode persistence and replay idempotency

**Files:**
- Create: `apps/api/core/intel/episode_store.py`
- Modify: `apps/api/core/live/episode_builder.py`
- Modify: `apps/api/core/live/vessel_episodes.py`
- Test: `tests/test_episode_store.py`

**Interfaces:**
- `episode_fingerprint(subject_ids, family, signal_ids, first_observed_at, last_observed_at, method_version) -> str`
- `save_episode(feature: dict[str, Any]) -> MaritimeEpisodeDB`
- `get_episode(episode_id: str)` and `list_episodes(...)` for internal consumers.

- [ ] Write RED tests proving deterministic fingerprint/ID and replay does not create duplicate rows.
- [ ] Implement minimal persistence using existing episode feature properties and append/update semantics only for the same deterministic episode identity.
- [ ] Run `pytest tests/test_episode_store.py tests/test_episode_builder.py tests/test_live_vessel_episodes.py -q` GREEN.
- [ ] Commit as `feat: persist deterministic maritime episodes`.
### Task 3: Fail-closed episode taxonomy and evidence-lineage aggregation

**Files:**
- Modify: `apps/api/core/live/episode_builder.py`
- Modify: `apps/api/core/live/vessel_episodes.py`
- Reuse: `apps/api/core/intel/evidence_lineage.py`
- Test: `tests/test_episode_builder.py`, `tests/test_live_vessel_episodes.py`

**Interfaces:**
- Unknown anomaly types return `unclassified_episode`; only explicit Safety signals return `safety_episode`.
- Every episode feature exposes `independence_groups`, `independent_source_count`, and `verification_status` using the existing lineage classifier.
- `behaviour_context` may be summarized on the episode but never contributes an independence group.

- [ ] Add RED tests for unknown→unclassified, explicit NUC→Safety, same-lineage gap+infra→one independence group, and two independent sources→corroborated.
- [ ] Implement the smallest taxonomy and aggregation changes using `evidence_lineage` as the sole source-independence authority.
- [ ] Run the focused episode/lineage tests GREEN.
- [ ] Commit as `fix: make maritime episodes lineage aware`.

### Task 4: Alternative-explanation contract and hypothesis eligibility

**Files:**
- Create: `apps/api/core/intel/hypothesis_eligibility.py`
- Modify: `apps/api/core/intel/hypothesis_engine.py`
- Test: `tests/test_hypothesis_eligibility.py`, `tests/test_hypothesis_engine.py`

**Interfaces:**
- `evaluate_hypothesis_eligibility(episode, events) -> EligibilityDecision` returns eligible/type/reason_codes/counter_indicators/evidence_stage.
- Low-specificity families (`gap`, `rendezvous`, `infrastructure`) require genuine independent corroboration before creating a v1 hypothesis.
- Position-spoofing may create candidate on high-specificity deterministic evidence, but one-lineage evidence never advances it beyond candidate.

- [ ] Write RED tests: one gap→no hypothesis; two same-lineage gap indicators→no hypothesis; independent corroboration→candidate/collecting according to gate; expected/unusual behaviour is not an extra source; spoof candidate stays candidate with one lineage.
- [ ] Implement eligibility as a separate pure module and route `evaluate_episode()` through it.
- [ ] Ensure every newly created hypothesis receives the episode ID and preserves counter-indicators.
- [ ] Run focused hypothesis tests GREEN.
- [ ] Commit as `fix: gate hypotheses on episode evidence`.
### Task 5: Live cutover and legacy isolation

**Files:**
- Modify: `apps/api/core/mda/watch.py`
- Modify: `apps/api/core/intel/hypothesis_store.py`
- Modify: `apps/api/core/intel/hypothesis_engine.py`
- Test: `tests/test_replay_end_to_end.py`, `tests/test_hypothesis_store.py`

**Interfaces:**
- Live scan persists/refreshes the episode before evaluating hypothesis eligibility.
- New v1 hypotheses must have non-null `episode_id`; legacy rows remain queryable and unchanged.
- Repeated scans/replays are idempotent for both episode and v1 hypothesis identity.

- [ ] Write RED end-to-end tests for episode persistence before hypothesis evaluation, v1 episode linkage, no relinking of legacy NULL rows, and replay idempotency.
- [ ] Implement the cutover in the real MDA scan path with no parallel second hypothesis engine.
- [ ] Run replay, store and live wiring tests GREEN.
- [ ] Commit as `feat: cut over live hypotheses to persisted episodes`.

### Task 6: Regression corpus, privacy, observability and release gate

**Files:**
- Modify: `tests/fixtures/osint/benign_service_vessels.jsonl`
- Modify: relevant replay/privacy/publication tests
- Modify: `apps/api/core/observability.py` only if counters need new episode/v1-hypothesis dimensions
- Modify: `docs/current_work.md`, `prompt.md`

**Interfaces:**
- YOUR WISDOM same-lineage normal-service fixture: internal episode, zero hypothesis, zero Case, zero public allegation.
- Contrastive same identity: `unusual` behaviour is retained as context but still obeys hypothesis evidence gates.
- New counters distinguish observations→episodes and episodes→v1 hypotheses without exposing vessel identity.

- [ ] Add/adjust RED regression tests for YOUR WISDOM and contrastive context, Humanitarian privacy, Safety neutrality, and public hypothesis gate.
- [ ] Make only the minimal wiring/observability changes needed for GREEN.
- [ ] Run full backend tests, Ruff critical gate, canonical mypy, Alembic checks, all web suites/lint/build, edge tests/Wrangler, privacy/lineage/vessel-marker regressions, and `git diff --check`.
- [ ] Inspect the exact diff for hard-coded vessel exceptions, accidental legacy mutation, Safety fallback, and evidence-stage inflation.
- [ ] Commit documentation/verification updates as `docs: align observation episode hypothesis v1`.
- [ ] Push one PR; merge only after exact-head Full CI + CodeQL are green. Production migration/restart remains a separate explicitly authorized rollout step.
