# DSC + NAVTEX Structured Evidence v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize already-demodulated DSC and NAVTEX messages into replayable Maritime structured evidence without pulling continuous audio/voice intelligence into this packet.

**Architecture:** Packet D consumes the provider-neutral remote-radio layer and immutable SourceObservation model created by Remote Maritime Radio v1. DSC and NAVTEX inputs are structured decoder output/text, not stored waveform/audio. DSC emergency evidence is Maritime Safety by default; NAVTEX is contextual/corroborative. Neither signal type alone creates a Humanitarian incident or mutates canonical lifecycle.

**Tech Stack:** Python 3.12, frozen dataclasses, existing `SourceObservationDB`, `IntelEvent`, service taxonomy, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md`

## Global Constraints

- Source identity != transport/provider != physical receiver/RF lineage.
- Reuse `radio_receiver:<physical_lineage>` as the physical evidence source boundary.
- No continuous audio/IQ persistence or voice transcription in this packet.
- DSC/EPIRB-style emergency evidence defaults to `service=maritime`, `lane=safety`; never Humanitarian solely by signal type.
- NAVTEX defaults to Maritime contextual/corroborative evidence and cannot auto-resolve incidents.
- Persist bounded structured/raw-text evidence only; replay must be idempotent.
- Production decoder/runtime activation remains a separate operator decision.

---

### Task 0: Structured decoded-input contracts

**Files:**
- Create: `apps/api/core/radio/structured.py`
- Test: `tests/test_structured_radio_contracts.py`

**Interfaces:**
- Produces immutable `DSCObservation` and `NAVTEXObservation` dataclasses.
- Both carry `receiver_id`, `physical_lineage`, `observed_at`, `frequency_hz`, `source_terms`, `raw_evidence_ref` and deterministic decoder/message identity.
- DSC additionally carries bounded category, MMSI when present, coordinates when present, and distress/nature code.
- NAVTEX additionally carries station identifier, subject/message identifier, area when known, and bounded message text.

- [ ] RED: empty receiver/physical lineage/message identity fails closed; coordinates/frequency validate; unknown categories remain explicit `unknown`, never guessed.
- [ ] RED: DSC contract has no `service=humanitarian` shortcut and NAVTEX contract has no lifecycle/publication field.
- [ ] Run `pytest -q tests/test_structured_radio_contracts.py` and confirm failures because `core.radio.structured` does not exist.
- [ ] Implement frozen contracts plus bounded normalization helpers only; no parsing/persistence yet.
- [ ] Run contract tests GREEN and Ruff on the new module/test.
- [ ] Commit `feat: add DSC and NAVTEX structured evidence contracts`.

### Task 1: DSC decoder-output normalizer

**Files:**
- Create: `apps/api/core/radio/dsc.py`
- Test: `tests/test_dsc_decoder.py`

**Interfaces:**
- Consumes a bounded mapping from an external DSC decoder/NMEA bridge rather than waveform bytes.
- Produces `DSCObservation` with deterministic `decoder_message_id` and explicit field-presence provenance.

- [ ] RED fixtures: distress, urgency/safety/non-distress, MMSI present/absent, coordinates present/absent, malformed/partial input.
- [ ] RED contrastive: a DSC distress message yields Maritime Safety classification metadata and never Humanitarian metadata.
- [ ] Run the decoder tests RED.
- [ ] Implement deterministic mapping/validation; retain unknown/unsupported codes as bounded strings instead of inventing semantic meaning.
- [ ] Run DSC + beacon-compartment + service-taxonomy regressions GREEN.
- [ ] Commit `feat: normalize structured DSC evidence`.

### Task 2: NAVTEX block parser

**Files:**
- Create: `apps/api/core/radio/navtex.py`
- Test: `tests/test_navtex_parser.py`

**Interfaces:**
- Consumes already-demodulated NAVTEX text blocks (`ZCZC ... NNNN`) plus receiver provenance.
- Produces `NAVTEXObservation`; parser never performs voice/audio acquisition.

- [ ] RED fixtures: valid station/subject/serial header, multiline body, duplicate replay identity, malformed/no terminator, oversized body truncation/fail-closed behavior.
- [ ] RED contrastive: distress wording inside NAVTEX does not become a Humanitarian incident or direct lifecycle command.
- [ ] Run NAVTEX tests RED.
- [ ] Implement bounded header/body parser with deterministic message identity and explicit parse reason codes.
- [ ] Run NAVTEX + service-taxonomy/privacy regressions GREEN.
- [ ] Commit `feat: parse structured NAVTEX evidence`.

### Task 3: Immutable structured-radio SourceObservation bridge

**Files:**
- Create: `apps/api/core/radio/structured_source_observation.py`
- Test: `tests/test_structured_radio_source_observation.py`

**Interfaces:**
- Persists DSC as `service=maritime`, `lane=safety`, `observation_type=dsc_message`.
- Persists NAVTEX as Maritime contextual evidence with explicit type and physical receiver source identity.
- Uses existing `record_observation()`; no second truth store.

- [ ] RED: same decoder/message key replays idempotently; different provider frontends sharing physical lineage resolve to the same source entity boundary.
- [ ] RED: bounded raw text/structured payload contains no waveform/audio/IQ body and no lifecycle mutation.
- [ ] Run bridge tests RED.
- [ ] Implement thin persistence functions using `radio_receiver:<physical_lineage>` and source terms/provenance from the Remote Radio packet.
- [ ] Run SourceObservation/evidence-lineage/Humanitarian privacy regressions GREEN.
- [ ] Commit `feat: persist DSC and NAVTEX structured observations`.

### Task 4: Maritime Safety candidate projection

**Files:**
- Create: `apps/api/core/radio/safety_projection.py`
- Modify: `apps/api/core/intel/service_taxonomy.py` only if an explicit DSC observation type needs positive recognition.
- Test: `tests/test_dsc_safety_projection.py`

**Interfaces:**
- Produces a bounded Maritime Safety candidate/event from eligible DSC emergency observations.
- Does not create `HumanitarianIncidentDB`, does not resolve lifecycle, and does not promote NAVTEX to a direct emergency candidate.

- [ ] RED: DSC distress can produce a Maritime Safety candidate with receiver/evidence reference; non-distress DSC cannot.
- [ ] RED: DSC/EPIRB-style candidate appears only in Maritime Safety classification and never Humanitarian; NAVTEX stays context-only.
- [ ] RED: replay cannot duplicate a candidate or mutate an existing Humanitarian incident.
- [ ] Run projection + `tests/test_beacon_compartment.py` + service taxonomy tests RED/GREEN as appropriate.
- [ ] Implement the smallest additive projection path, reusing existing IntelEvent/Safety conventions rather than adding a parallel incident store.
- [ ] Commit `feat: project DSC maritime safety candidates`.

### Task 5: Runtime handoff, observability, and release gates

**Files:**
- Create/modify only the minimal structured-input runtime hook needed to accept configured decoder messages.
- Modify: `apps/api/core/observability.py`
- Modify: `docs/DATA_FLOW.md`
- Modify: `docs/OPERATIONS_OVERVIEW.md`
- Modify: `docs/current_work.md`
- Modify: `prompt.md`
- Modify: master loop + this execution record
- Test: nearest runtime/observability/config regressions

**Interfaces:**
- Runtime accepts bounded decoded DSC/NAVTEX input from configured adapters/bridges; no microphone/audio stream ownership.
- Metrics use bounded type/outcome labels only, never MMSI, receiver ID, station free text, message body, or session IDs.

- [ ] RED runtime/metric-cardinality/privacy tests.
- [ ] Implement disabled-by-default structured-input orchestration and bounded operator summary if needed.
- [ ] Run focused DSC/NAVTEX/source-observation/service/privacy/evidence-lineage regressions.
- [ ] Run full backend, Ruff critical, canonical mypy, migrations and canonical dependency audit; run web/edge if boundaries changed.
- [ ] Exact-diff review for Humanitarian fallback, lifecycle mutation, raw waveform/audio persistence, duplicate physical lineage, unbounded text/metrics, and provider-specific truth paths.
- [ ] Mark packet review-ready and hand off to Audio Evidence v1 only after all gates are green.
- [ ] Commit `docs: close DSC and NAVTEX structured evidence v1`.

## Exit Criteria

DSC + NAVTEX Structured Evidence v1 is complete when already-demodulated DSC/NAVTEX inputs normalize into immutable structured observations with physical receiver provenance; DSC emergency evidence can create only a Maritime Safety candidate; NAVTEX remains contextual/corroborative; replay is idempotent; no waveform/audio is stored; no signal type alone creates Humanitarian state; no lifecycle is silently mutated; and release gates/review are green.

## Rollback Boundary

The packet is additive. Rollback disables/removes structured decoder ingestion and projection code while retaining immutable SourceObservations already written for audit. No Humanitarian lifecycle repair or public data migration is required.
