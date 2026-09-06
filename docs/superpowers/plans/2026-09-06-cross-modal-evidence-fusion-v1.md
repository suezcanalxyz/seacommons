# Cross-modal Evidence Fusion v1 Implementation Plan

**Goal:** combine Humanitarian, AIS, DSC/NAVTEX, remote-radio and audio-derived evidence without collapsing provenance, double-counting modalities, or allowing derived/model output to become canonical truth.

**Architecture:** all inputs remain references to immutable/replayable evidence objects. Fusion computes a bounded `EvidencePacket` and derived assessments only; source independence is lineage-based and modality-aware. Contradictions are preserved explicitly.

## Permanent boundaries

- Observation/artifact/transcript != incident/episode/assessment/review/public projection.
- Same source identity or physical receiver across transports/frontends is one lineage.
- Multiple AIS providers remain one AIS modality for independence.
- Derived AIS behaviour and audio transcripts do not add source independence.
- Humanitarian privacy boundary remains intact; no MMSI/IMO/callsign leaks to Humanitarian public output.
- No fusion result directly mutates lifecycle or publishes allegations.

### Task 0: Provider-neutral evidence packet contracts

- Create immutable evidence references with `evidence_id`, `evidence_class`, `source_lineage`, `modality`, `observed_at`, `confidence`, and `derived`.
- Build immutable `CrossModalEvidencePacket` with explicit independence groups, contradictions, missing evidence classes, and confidence ceiling.
- RED tests for deterministic identity, bounded vocabularies, duplicate-lineage collapse, AIS-provider same-modality handling, and derived evidence not increasing independence.
- Commit `feat: add cross-modal evidence packet contracts`.

### Task 0 execution record — 2026-09-06

- `EvidenceReference` and `CrossModalEvidencePacket` are frozen, deterministic and bounded.
- Source-lineage is authoritative for independence except AIS, which collapses to `modality:ais`; derived evidence contributes no independence key.
- Duplicate evidence IDs, required classes and contradiction labels deduplicate deterministically; missing evidence classes and confidence ceiling are explicit.
- Focused cross-modal/lineage/AIS/transcript gate: `33 passed`; Ruff and `git diff --check` green.

### Task 1: Independence and contradiction engine

- Compute independent lineage/modality groups without provider-count inflation.
- Preserve contradiction records instead of averaging confidence.
- Commit `feat: evaluate cross-modal evidence independence`.

### Task 1 execution record — 2026-09-06

- `CrossModalIndependenceAssessment` reports bounded `single_lineage | multi_lineage | contradictory` states only.
- Contradictions retain explicit topic/reason/evidence IDs and must reference evidence present in the packet.
- Same physical receiver across radio/audio remains one source group; all direct AIS providers remain `modality:ais`; derived evidence is counted but never increases independence.
- Focused Task 1 gate: `29 passed`; Ruff and `git diff --check` green.

### Task 2: Humanitarian resolution context bridge

- Feed cross-modal context into ResolutionAssessment as evidence references only; no lifecycle mutation.
- AIS/audio-derived evidence may support context but cannot alone confirm rescue.
- Commit `feat: add cross-modal humanitarian resolution context`.

### Task 2 execution record — 2026-09-06

- Cross-modal Humanitarian context is attached only to the persisted `resolution` assessment JSON; the existing outcome/confidence/review semantics are untouched.
- Context exposes evidence IDs/classes, direct modalities, independent-group count, contradiction topics, missing classes and confidence ceiling only; source-lineage/receiver/MMSI remain absent.
- AIS and derived audio/transcript context cannot confirm rescue by themselves.
- Focused Humanitarian bridge/resolution regressions: `40 passed, 1 warning`; Ruff and diff check green.

### Task 3: Maritime episode context bridge

- Attach DSC/NAVTEX/radio/audio evidence to MaritimeEpisode/hypothesis context with replayable provenance.
- Commit `feat: add cross-modal maritime episode context`.

### Task 3 execution record — 2026-09-06

- Cross-modal Maritime context persists only under `MaritimeEpisode.behaviour_context.cross_modal_context`.
- Episode identity/status/fingerprint/native independence groups remain unchanged; linked hypothesis state/evidence_links/review flags are not mutated.
- Context is bounded and omits source-lineage/receiver identifiers.
- Focused episode/hypothesis gate: `24 passed`; Ruff and `git diff --check` green.

### Task 4: Observability, privacy and release gates

- Bounded metrics, exact diff review, focused/full/static/migrations/audit.
- Hand off to Review v0/publication controls only after green/reviewed.
