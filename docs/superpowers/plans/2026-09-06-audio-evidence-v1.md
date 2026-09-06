# Audio Evidence v1 — implementation plan

**Goal:** add bounded, legally-permitted audio as immutable evidence artifacts without creating a second truth store or pulling transcription/AI into canonical decision authority.

**Architecture:** `EvidenceArtifact(type=audio)` is provenance-bearing storage linked to physical receiver lineage and SourceObservation IDs. Acquisition is disabled by default and fail-closed on unclear terms/retention. Transcript and claim extraction are derived objects in later tasks; no transcript/model output mutates Humanitarian lifecycle or public allegations.

## Packet boundaries

- Bounded clips only; no continuous recording.
- Explicit `physical_lineage`, receiver ID, frequency/channel, start/end, content hash, MIME/codec metadata, source terms and retention policy.
- No raw audio bytes inside SourceObservation JSON/provenance.
- Artifact storage reference and hash are immutable; retention policy is explicit and auditable.
- Acquisition/runtime remains disabled by default.
- No transcription in Task 0; later transcript objects must be derived and replayable.

### Task 0: Immutable audio artifact contract

**Files:** create `apps/api/core/evidence/audio_artifact.py`; tests `tests/test_audio_artifact_contract.py`.

- [ ] RED: frozen artifact requires physical lineage, receiver, frequency, timezone-aware start/end, content hash, storage reference, MIME/codec, source terms and bounded retention.
- [ ] RED: invalid duration/hash/retention/terms fail closed; artifact has no `humanitarian`, `lifecycle`, `publication`, `transcript`, or model-decision fields.
- [ ] Implement minimum frozen contract and deterministic artifact ID.
- [ ] Run focused provider/source-observation/privacy regressions GREEN.
- [ ] Commit `feat: add immutable audio evidence artifact contract`.

### Task 1: Artifact persistence boundary

- Persist artifact metadata/reference immutably using the existing evidence/provenance model or the smallest additive store if no suitable durable object exists.
- Replay by content hash + physical lineage is idempotent.
- Never embed audio bytes in DB JSON or SourceObservation.

### Task 2: Bounded acquisition policy

- Disabled by default.
- Require provider/source terms status `allowed`, explicit max clip duration, retention policy and configured storage destination.
- No continuous rolling capture.

### Task 3: Derived transcript contract

- Transcript is derived from artifact ID/hash, versioned by engine/model, replayable, and non-canonical.
- No transcript/model output may create/resolve Humanitarian lifecycle or publish allegations.

### Task 4: Release gates and handoff

- Focused audio/provenance/privacy regressions; full backend/static/migrations/dependency audit.
- Exact-diff review for continuous recording, unbounded retention, raw-byte DB persistence, source-lineage inflation, Humanitarian/lifecycle mutation and model authority.
- Hand off to Cross-modal Evidence Fusion v1 only after green/reviewed.

## Exit criteria

Audio Evidence v1 is complete when bounded audio artifacts have immutable provenance, explicit retention/source terms, disabled-by-default acquisition, idempotent storage, derived-only transcripts, and no audio/transcript/model path can silently mutate canonical truth or public allegations.
