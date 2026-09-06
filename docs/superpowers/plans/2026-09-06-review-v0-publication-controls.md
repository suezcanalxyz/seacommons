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
