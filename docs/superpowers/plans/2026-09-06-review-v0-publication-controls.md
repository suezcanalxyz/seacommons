# Review v0 / Publication Controls Implementation Plan

**Goal:** add one auditable review mechanism over existing Humanitarian ResolutionAssessment and Maritime InvestigationHypothesis workflows without creating a second truth store or a publication shortcut.

**Architecture:** `ReviewRecord` captures the reviewed object, immutable evidence snapshot, decision, rationale, reviewer identity/time and requested transition. Applying a review delegates to the existing Humanitarian lifecycle/publication or Maritime hypothesis/publication gates; review itself never writes canonical truth directly.

## Permanent boundaries

- Review record != incident/hypothesis/assessment/public projection.
- Evidence snapshot is references + hashes/versions, not copied raw evidence.
- No review path may expose Humanitarian MMSI/IMO/callsign/tracker dossier data.
- `approve` never means “publish”; the requested transition must still pass the domain-specific gate.
- Rejection/needs-more-evidence never destructively deletes evidence.
- Every apply action is replay-safe and auditable.

### Task 0: Immutable review record contract

- Create frozen `ReviewRecord` with deterministic review ID, target type/id/version, evidence packet/snapshot ID, decision, rationale, actor, reviewed_at and requested transition.
- Bounded vocabularies; no direct lifecycle/publication fields or raw evidence body.
- RED tests for deterministic identity, fail-closed values, replay semantics and privacy-safe snapshot references.
- Commit `feat: add review record contract`.

### Task 0 execution record — 2026-09-06

- `ReviewRecord` is frozen and deterministic from target/version/snapshot/decision/rationale/actor/time/requested transition.
- Decisions are bounded to `approve | reject | needs_more_evidence`; approve requires a target-specific requested transition, and no transition can request direct publication.
- Snapshot is an opaque reference only; raw/sensitive prefixes including MMSI/IMO/callsign/transcript are rejected.
- Contract contains no lifecycle/publication/raw evidence fields.
- Focused Task 0 gate: `15 passed`; Ruff and `git diff --check` green.

### Task 1: Durable review ledger

- Persist append-only/replay-safe review records with target/version uniqueness semantics and audit timestamps.
- No mutation of target objects in the ledger layer.
- Commit `feat: persist review audit records`.

### Task 2: Humanitarian review application adapter

- Apply accepted review only through existing Humanitarian transition/review mechanisms; preserve privacy and ResolutionAssessment evidence.
- Contradictory/insufficient evidence remains review-required; no automatic resolution.
- Commit `feat: apply humanitarian review decisions safely`.

### Task 3: Maritime hypothesis review application adapter

- Apply review through `InvestigationHypothesis` transition/publication gates; allegation-shaped wording still requires explicit review and publication policy.
- Commit `feat: apply maritime hypothesis review decisions safely`.

### Task 4: Operator surface, observability and release gates

- Bounded review metrics and operator-safe summaries.
- Full privacy/publication/replay gates, full backend/static/migrations/audit, web/edge if contracts cross boundaries.
- Exact diff review for bypasses, destructive evidence changes, sensitive identifiers and duplicate truth stores.


### Task 1 execution record — 2026-09-06

- Added append-only `ReviewRecordDB` ledger and migration `0023_review_records`.
- Exact replay is idempotent by `review_id`; distinct decisions/versions append distinct records.
- Ledger stores review metadata/references only and never mutates Assessment/Hypothesis targets.

### Task 2 execution record — 2026-09-06

- Humanitarian review validates the current ResolutionAssessment version before ledger persistence.
- Approved transitions create audited `IncidentTransitionDB` rows with `review_decision_id`; reject/needs-more-evidence do not advance lifecycle.
- Direct publication remains unavailable from the review contract.

### Task 3 execution record — 2026-09-06

- Maritime review delegates state changes to the existing `InvestigationHypothesis.transition()` state machine.
- Replay identity is the exact `review_id`, not reviewer identity; stale target versions fail before ledger persistence.
- Review may attest `explicit_review_done`, but `published` is excluded from ReviewRecord transitions and remains behind the existing publication gate.

### Task 4 / release record — 2026-09-06

- Added bounded review metrics and an operator-safe recent-review summary that omits rationale and evidence snapshot contents.
- Exact-diff review found and fixed two Important issues: actor-based Maritime replay identity and stale-review persistence before target validation; also aligned review transition vocabulary with the real Maritime state machine while continuing to exclude `published`.
- Final code HEAD `19dbb7d`: focused review/privacy/publication gate `181 passed, 1 warning`; full backend `1519 passed, 2 skipped, 221 warnings`; Ruff and canonical mypy green; clean Alembic upgrade through `0023_review_records`; canonical project dependency audit reports no known vulnerabilities.
- Web tests/lint/typecheck/build/audit green (pre-existing Vite large-chunk warning only); edge `12 passed`, Wrangler dry-run green, audit green.
- Review v0 is development-complete / review-ready. No production migration, restart, deploy, audio capture, feed activation, or automatic publication was performed.
