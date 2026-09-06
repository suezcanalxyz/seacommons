# Remote Maritime Radio v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a software-only, provider-neutral remote maritime-radio acquisition layer that can discover/configure permitted KiwiSDR/OpenWebRX receivers, expose receiver health/capability/provenance, and emit normalized bounded `RadioObservation` metadata without continuous audio recording or canonical incident mutation.

**Architecture:** Remote receiver transports normalize into a shared contract before any DSC/NAVTEX/audio reasoning. Receiver identity is distinct from provider/frontend identity and from physical RF lineage, so two frontends exposing one receiver never count as independent evidence. v1 persists only bounded receiver/signal observations through the existing `SourceObservation` path; raw audio/IQ persistence and decoding belong to later packets.

**Tech Stack:** Python 3.12, dataclasses/Protocols, FastAPI runtime/config, existing `SourceObservationDB`, pytest, Prometheus observability, HTTP/WebSocket clients already present in the API environment.

**Spec:** `docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md`

## Global Constraints

- Software-only remote receivers; SeaCommons-owned SDR hardware is not a core requirement.
- Do not extend `core.sensors.sdr.SDRScanner` into the remote receiver path; that module remains the legacy local-hardware anomaly scanner.
- No continuous voice recording and no raw audio/IQ persistence in this packet.
- No DSC/NAVTEX decoding in this packet; Packet D consumes the normalized receiver layer.
- Source/provider/frontend identity != physical receiver identity != RF lineage.
- Multiple URLs/frontends for one physical receiver never become independent corroboration.
- Unsupported, inaccessible, rate-limited, or unclear-terms receivers fail closed and expose health/error state.
- Remote radio observations never create Humanitarian incidents, resolve lifecycle, or publish allegations.
- Every durable observation uses the existing immutable/idempotent `record_observation()` path.

---

### Task 0: Provider-neutral receiver and observation contracts

**Files:**
- Create: `apps/api/core/radio/__init__.py`
- Create: `apps/api/core/radio/provider.py`
- Test: `tests/test_radio_provider.py`

**Interfaces:**
- Produces `ReceiverCapability`, `RemoteReceiverHealth`, `RadioObservation`, `ObservationCallback`, and `RemoteReceiverAdapter`.
- `RadioObservation` contains only bounded metadata: `receiver_id`, `provider`, `physical_lineage`, `frequency_hz`, `mode`, `observed_at`, optional signal level/SNR, `source_terms`, and optional provider message/session id.

- [x] Write RED tests proving provider names normalize deterministically, invalid/empty receiver identity fails closed, and two provider frontends may share one `physical_lineage`.
- [x] Run `pytest -q tests/test_radio_provider.py` and observe the expected import/contract failures.
- [x] Implement frozen dataclasses and a `Protocol` with `start()`, `stop()`, `health()`, `capabilities()`, and `tune(frequency_hz, mode)`; do not add persistence or decoding.
- [x] Run `pytest -q tests/test_radio_provider.py` GREEN and `python -m ruff check core/radio/provider.py` from `apps/api`.
- [x] Commit `feat: add remote radio provider contract`.

### Task 1: Receiver identity, capability registry, and physical lineage

**Files:**
- Create: `apps/api/core/radio/registry.py`
- Modify: `apps/api/core/config.py`
- Test: `tests/test_remote_receiver_registry.py`

**Interfaces:**
- Produces `ReceiverDescriptor` and `ReceiverRegistry` with deterministic `receiver_id`, provider/frontend URL, physical lineage, geographic coordinates when known, supported frequency ranges/modes, source terms, enabled flag, and bounded operator notes.
- Consumes provider-neutral capability types from Task 0.

- [x] Write RED tests for deterministic identity, duplicate frontend collapse by physical lineage, disabled/unclear-terms receivers excluded from runnable candidates, and bounded configured receiver count.
- [x] Run `pytest -q tests/test_remote_receiver_registry.py` and confirm failures are due to the missing registry.
- [x] Implement explicit configured descriptors only; no unbounded internet crawling or automatic trust of directory metadata.
- [x] Add fail-closed config values for `REMOTE_RADIO_ENABLED`, maximum configured receivers, connect timeout, and optional receiver descriptor JSON/file path; default disabled.
- [x] Run registry tests plus `tests/test_config.py` or the nearest config regression file GREEN.
- [x] Commit `feat: add remote receiver identity registry`.

### Task 2: KiwiSDR remote adapter

**Files:**
- Create: `apps/api/core/radio/kiwisdr.py`
- Test: `tests/test_kiwisdr_adapter.py`

**Interfaces:**
- Implements `RemoteReceiverAdapter` for one configured KiwiSDR endpoint.
- Emits normalized `RadioObservation` metadata through the Task 0 callback; v1 does not persist audio bytes.

- [ ] Write RED fixture tests for connection/handshake metadata normalization, bounded tune validation, health transitions, source-terms propagation, and disconnect/error fail-closed behavior.
- [ ] Add a contrastive RED test proving the adapter never writes an audio artifact or Humanitarian incident.
- [ ] Run `pytest -q tests/test_kiwisdr_adapter.py` and observe the expected failures.
- [ ] Implement the smallest transport wrapper needed for configured endpoints, with dependency injection for network I/O so tests never require the public internet.
- [ ] Enforce configured frequency/mode capability bounds before network calls and expose `connected`, `last_message_at`, `observations_received`, and bounded `error` in health.
- [ ] Run adapter tests GREEN and focused source-observation/privacy regressions.
- [ ] Commit `feat: add KiwiSDR remote receiver adapter`.

### Task 3: OpenWebRX remote adapter

**Files:**
- Create: `apps/api/core/radio/openwebrx.py`
- Test: `tests/test_openwebrx_adapter.py`

**Interfaces:**
- Implements the same Task 0 `RemoteReceiverAdapter` contract without leaking OpenWebRX-specific shapes downstream.
- Reuses receiver identity/physical lineage from Task 1 rather than deriving independence from URL/provider count.

- [ ] Write RED fixtures for OpenWebRX metadata/session normalization, tune capability rejection, health transitions, and source-terms propagation.
- [ ] Write RED proving a KiwiSDR and OpenWebRX frontend configured with the same `physical_lineage` remain one evidence lineage.
- [ ] Run `pytest -q tests/test_openwebrx_adapter.py tests/test_remote_receiver_registry.py` and confirm expected failures.
- [ ] Implement the minimal adapter using injected transport functions and the same bounded observation contract as KiwiSDR.
- [ ] Run the adapter/registry tests GREEN.
- [ ] Commit `feat: add OpenWebRX remote receiver adapter`.

### Task 4: Immutable radio SourceObservation bridge

**Files:**
- Create: `apps/api/core/radio/source_observation.py`
- Test: `tests/test_radio_source_observation.py`

**Interfaces:**
- Consumes normalized `RadioObservation` from Tasks 0/2/3.
- Persists idempotent `SourceObservation` rows with `service="maritime"`, a non-Humanitarian radio acquisition lane/observation type compatible with current taxonomy, and provenance containing receiver/provider/physical-lineage/source-terms metadata.

- [ ] Write RED proving replay of the same provider observation/session key is idempotent, provider URL is not treated as physical independence, and provenance keeps receiver/physical lineage/source terms.
- [ ] Write RED proving no audio/IQ body, transcript, MMSI-derived Humanitarian classification, or lifecycle mutation is created by this bridge.
- [ ] Run `pytest -q tests/test_radio_source_observation.py` and observe expected failures.
- [ ] Implement a thin bridge around `core.intel.source_observation.record_observation()`; store only bounded text/JSON metadata as `raw_payload`, never continuous waveform content.
- [ ] Run source-observation, evidence-lineage, Humanitarian privacy, and service-taxonomy regressions GREEN.
- [ ] Commit `feat: persist bounded remote radio observations`.

### Task 5: Runtime, health, observability, and operator surface

**Files:**
- Create: `apps/api/core/radio/runtime.py`
- Modify: `apps/api/core/observability.py`
- Modify: `apps/api/core/api/routes/ops.py` or the existing operator status route that already hosts source health
- Modify: `apps/api/core/bootstrap.py` only if this is the established startup registration point
- Test: `tests/test_radio_runtime.py`
- Test: `tests/test_observability.py`

**Interfaces:**
- Starts only enabled/configured/terms-allowed receivers when `REMOTE_RADIO_ENABLED=true`; default runtime is disabled.
- Exposes bounded labels only: provider, health state, mode class, and outcome. Never label metrics with receiver URLs, station free text, session IDs, callsigns, MMSI, or arbitrary frequency values.

- [ ] Write RED tests for disabled-by-default startup, partial provider failure isolation, stop semantics, duplicate physical-lineage suppression, and bounded health/status output.
- [ ] Write RED metric-cardinality tests using hostile receiver/session strings and assert they normalize to bounded labels.
- [ ] Run runtime/observability tests and observe expected failures.
- [ ] Implement runtime orchestration and operator-safe status without any public Live contract change.
- [ ] Run runtime/observability/config/bootstrap regressions GREEN.
- [ ] Commit `feat: orchestrate remote maritime radio receivers`.

### Task 6: Release gates and handoff to DSC + NAVTEX

**Files:**
- Modify: `docs/DATA_FLOW.md`
- Modify: `docs/OPERATIONS_OVERVIEW.md`
- Modify: `docs/current_work.md`
- Modify: `prompt.md`
- Modify: `docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md`
- Modify: this plan execution record

- [ ] Run focused remote-radio contract/registry/provider/source-observation/runtime/privacy/evidence-lineage regressions.
- [ ] Run full backend suite, Ruff critical gate, canonical mypy gate, migrations, and dependency audit.
- [ ] Run web/edge gates only if public/operator contracts crossed those boundaries; otherwise document why they are unchanged.
- [ ] Review exact diff for hidden audio persistence, duplicate physical lineage, unbounded discovery/metrics, Humanitarian fallback, lifecycle mutation, and provider-specific truth paths.
- [ ] Document provider/source-terms constraints and explicit no-continuous-recording boundary.
- [ ] Mark Remote Maritime Radio v1 review-ready with runtime disabled by default; production receiver activation remains an operator decision.
- [ ] Advance the master loop to DSC + NAVTEX only after the packet is green and reviewed.
- [ ] Commit `docs: close remote maritime radio v1 release gates`.

## Exit Criteria

Remote Maritime Radio v1 is complete when configured KiwiSDR/OpenWebRX receiver frontends normalize through one provider-neutral contract; receiver identity and physical RF lineage are explicit; duplicate frontends cannot inflate source independence; health/capability/source terms are observable with bounded labels; bounded radio metadata persists immutably through SourceObservation; no continuous audio/IQ is stored; no DSC/NAVTEX decoding or lifecycle mutation occurs; runtime is disabled by default; and the full packet release gate is green.

## Rollback Boundary

The packet is additive and disabled by default. Rollback is configuration/code rollback to `REMOTE_RADIO_ENABLED=false`; no Humanitarian lifecycle or public projection needs repair. Any immutable SourceObservations already recorded remain auditable evidence and are not destructively deleted.
