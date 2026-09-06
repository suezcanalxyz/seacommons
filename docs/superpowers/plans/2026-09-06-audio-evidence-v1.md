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

- [x] RED: frozen artifact requires physical lineage, receiver, frequency, timezone-aware start/end, content hash, storage reference, MIME/codec, source terms and bounded retention.
- [x] RED: invalid duration/hash/retention/terms fail closed; artifact has no `humanitarian`, `lifecycle`, `publication`, `transcript`, or model-decision fields.
- [x] Implement minimum frozen contract and deterministic artifact ID.
- [x] Run focused provider/source-observation/privacy regressions GREEN.
- [x] Commit `feat: add immutable audio evidence artifact contract`.

### Task 0 execution record — 2026-09-06

- `AudioEvidenceArtifact` is frozen and deterministic from physical lineage + content hash + clip window.
- Maximum clip duration is 300 seconds; allowed retention policies are `24h | 7d | 30d`; source terms, audio MIME, codec, storage reference and at least one SourceObservation link are mandatory.
- Contract exposes no Humanitarian/lifecycle/publication/transcript/model-decision authority.
- Focused artifact/radio/source-observation/Humanitarian gate: `55 passed, 1 warning`; Ruff and `git diff --check` green.

### Task 1: Artifact persistence boundary

- Persist artifact metadata/reference immutably using the existing evidence/provenance model or the smallest additive store if no suitable durable object exists.
- Replay by content hash + physical lineage is idempotent.
- Never embed audio bytes in DB JSON or SourceObservation.

### Task 1 execution record — 2026-09-06

- Added metadata-only `audio_evidence_artifacts` store and migration `0022_audio_artifacts`.
- Artifact persistence is idempotent by deterministic artifact ID; same content on different physical lineages remains distinct evidence identity.
- Database schema stores hash/reference/provenance/retention/SourceObservation links only; no audio bytes, blob, waveform, IQ, transcript, Humanitarian/lifecycle/publication/model fields exist.
- Focused store/contract/migration gate: `19 passed`; migration upgrades cleanly through 0022. Extended source-observation/Humanitarian regressions green.

### Task 2: Bounded acquisition policy

- Disabled by default.
- Require provider/source terms status `allowed`, explicit max clip duration, retention policy and configured storage destination.
- No continuous rolling capture.

### Task 2 execution record — 2026-09-06

- Added pure `AudioAcquisitionPolicy`; no recorder/transport/network ownership exists in this task.
- Defaults: disabled, max clip 60s, retention `7d`, storage prefix empty. Enabling only the flag cannot authorize capture.
- Capture authorization additionally requires configured storage, allowed retention, exact `terms_status=allowed`, non-empty source terms, and positive duration within policy cap; absolute maximum is 300s.
- Focused policy/config/artifact/store gate: `35 passed`; Ruff and `git diff --check` green.

### Task 3: Derived transcript contract

- [x] Transcript is derived from artifact ID/hash, versioned by engine/model, replayable, and non-canonical.
- [x] No transcript/model output may create/resolve Humanitarian lifecycle or publish allegations.

### Task 3 execution record — 2026-09-06

- `DerivedAudioTranscript` is frozen, deterministic, bounded to 20,000 characters, and versioned by engine/model/model_version.
- It exposes `derived=True` and `canonical_authority=False`; no Humanitarian/lifecycle/publication/decision fields exist.
- Focused transcript/artifact/store/policy gate: `34 passed`; Ruff and `git diff --check` green.

### Task 4: Release gates and handoff

- [x] Focused audio/provenance/privacy regressions; full backend/static/migrations/dependency audit.
- [x] Exact-diff review for continuous recording, unbounded retention, raw-byte DB persistence, source-lineage inflation, Humanitarian/lifecycle mutation and model authority.
- [x] Hand off to Cross-modal Evidence Fusion v1 only after green/reviewed.

### Task 4 execution record — 2026-09-06

- Focused audio/privacy/provenance gate: `80 passed, 1 warning`.
- Full backend: `1458 passed, 2 skipped, 221 warnings`.
- Ruff critical, canonical mypy, migrations through `0022_audio_artifacts`, and canonical project dependency audit are green.
- Exact diff confirms metadata-only DB persistence, bounded retention, disabled-by-default acquisition, no continuous recorder ownership, no source-lineage inflation, and no Humanitarian/lifecycle/model authority path.
- Audio Evidence v1 is development-complete/review-ready. Production audio capture remains disabled and requires explicit operator authorization.

## Exit criteria

Audio Evidence v1 is complete when bounded audio artifacts have immutable provenance, explicit retention/source terms, disabled-by-default acquisition, idempotent storage, derived-only transcripts, and no audio/transcript/model path can silently mutate canonical truth or public allegations.
