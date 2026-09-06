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
