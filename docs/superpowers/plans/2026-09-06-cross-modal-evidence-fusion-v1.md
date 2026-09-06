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

### Task 1: Independence and contradiction engine

- Compute independent lineage/modality groups without provider-count inflation.
- Preserve contradiction records instead of averaging confidence.
- Commit `feat: evaluate cross-modal evidence independence`.

### Task 2: Humanitarian resolution context bridge

- Feed cross-modal context into ResolutionAssessment as evidence references only; no lifecycle mutation.
- AIS/audio-derived evidence may support context but cannot alone confirm rescue.
- Commit `feat: add cross-modal humanitarian resolution context`.

### Task 3: Maritime episode context bridge

- Attach DSC/NAVTEX/radio/audio evidence to MaritimeEpisode/hypothesis context with replayable provenance.
- Commit `feat: add cross-modal maritime episode context`.

### Task 4: Observability, privacy and release gates

- Bounded metrics, exact diff review, focused/full/static/migrations/audit.
- Hand off to Review v0/publication controls only after green/reviewed.
