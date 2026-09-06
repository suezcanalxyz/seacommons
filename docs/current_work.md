# Current work — Evidence Fusion Development Loop

> **Canonical loop:** `docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md`
> **Current packet:** Free/Open AIS Fusion v1 — Task 8 release gates
> **Current packet plan:** `docs/superpowers/plans/2026-09-06-free-open-ais-fusion-v1.md`
> **Production runtime baseline:** `0ae4df7cc20c8209acc267eb595129c2dc3961bd`
> **Production schema:** `0021_maritime_episodes`

## Production baseline

OSINT Evidence Pipeline v1, Vessel Context + Behavioural Baseline v1, and Observation -> Episode -> Hypothesis v1 are merged, deployed and production-verified. Production keeps the Humanitarian privacy boundary, shared Live/Play vessel-marker contract, and evidence-lineage semantics where detector/provider multiplicity is not source independence.

The Evidence Fusion work is being developed in an isolated branch/worktree and is not yet production-active.

## Current packet state

Free/Open AIS Fusion v1 Tasks 0-7 are implemented and committed. The packet adds:

- compatibility-preserving AIS event bus;
- normalized `AISPositionObservation` + provider health contract;
- AISStream adapter under the normalized contract;
- Open Waters/aiscast software-only free adapter;
- conservative multi-provider reconciliation with upstream/station/source-terms provenance;
- coverage-aware gap reasoning extending the existing authoritative MDA classifier;
- reconciled AIS context in SAR Mission Assessment;
- runtime modes `legacy | shadow | fused`, default `legacy`, with instant rollback;
- provider-health propagation, bounded metrics and existing coverage-change audit logging.

Task 8 remains: docs alignment, exact-head backend/static/web/edge gates, review, and final branch readiness.
## Loop order after AIS

1. Humanitarian Verification v1 — NGO/IOM source roles, claim extraction, incident association, ResolutionAssessment.
2. Remote Maritime Radio v1 — software-only remote receiver abstraction and source/receiver health.
3. DSC + NAVTEX structured evidence.
4. Audio Evidence v1 — immutable bounded audio artifacts, transcription as derived evidence only.
5. Cross-modal Evidence Fusion v1 — combine Humanitarian, AIS and radio while preserving lineage independence.
6. Review v0 / publication controls on top of the real evidence workflows.

Each packet must ship independently testable software. The loop does not skip a packet because later functionality is more interesting.

## Core domain rules

Alarm Phone is currently the Humanitarian incident-creation authority, not the only Humanitarian source. SOS Mediterranee, MSF, Sea-Watch, Open Arms and similar first-party NGO sources remain Humanitarian verification sources. IOM Missing Migrants is archive/reference. A future Alarm Phone email/webhook adapter must normalize to the same source identity as X/Twikit; transport never changes business authority.

NGO AIS behaviour may establish `response_detected` or `rescue_activity_probable`, but AIS alone never confirms rescue. Explicit NGO rescue claims can contribute to `rescue_confirmed` only after strong association with the Alarm Phone incident; ambiguous matches require review.

Radio/audio follows the same model: adapters produce observations/artifacts; source/receiver identity and physical lineage are preserved; derived transcripts/claims cannot silently mutate canonical lifecycle.

## Execution discipline

TDD RED -> GREEN for every behavior change, one semantic commit per task, focused regression gate before advancing, full release gate at packet completion, code review before merge readiness, and documentation/status updates in the same cycle. Production deploy/migration/restart remains separately controlled.