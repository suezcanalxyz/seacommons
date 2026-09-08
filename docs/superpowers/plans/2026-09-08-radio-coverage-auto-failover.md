# Radio Coverage & Auto-Failover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded channel-aware receiver assignments, standby promotion and automatic failover to the existing remote-radio runtime without changing evidence semantics or persisting audio.

**Architecture:** Keep the persistent receiver catalog as the coverage/ranking authority. Add a pure failover planner that groups unique physical lineages by channel target, then extend `RemoteRadioRuntime` with an optional managed mode that starts only a bounded replica set and promotes ranked standby receivers on disconnect/staleness. Public status exposes aggregate channel coverage only.

**Tech Stack:** Python 3.12, dataclasses, threading, FastAPI status contracts, Prometheus, pytest, existing KiwiSDR/OpenWebRX adapters.

**Spec:** `docs/superpowers/specs/2026-09-08-radio-coverage-auto-failover-design.md`

## Global Constraints

- `AUDIO_EVIDENCE_ENABLED` remains false.
- No audio/IQ persistence or new evidence authority.
- Physical lineage is the independence boundary.
- Default managed replica count is 3; valid range 1–8.
- Managed failover defaults disabled until production activation.
- No DB migration.
- Disabled managed mode preserves current start-all/reconnect behavior.
- Every behavior change follows RED -> GREEN TDD.

---

## File map

- Create `apps/api/core/radio/failover.py`: channel target and deterministic assignment planning.
- Modify `apps/api/core/radio/runtime.py`: managed active/standby/cooldown lifecycle.
- Modify `apps/api/core/radio/public_pool.py`: build ranked candidates for explicit channel targets.
- Modify `apps/api/core/radio/catalog_store.py`: preserve requested channel kind in ranked descriptors.
- Modify `apps/api/core/config.py`: bounded failover settings.
- Modify `apps/api/core/acquisition/status.py` and `apps/api/core/radio/bridge.py`: public-safe channel summaries.
- Modify `apps/api/core/observability.py`: bounded failover outcomes.
- Test primarily in `tests/test_radio_failover.py`, `tests/test_radio_runtime.py`, `tests/test_live_pipeline_status.py`, `tests/test_observability.py`.

### Task 1: Pure channel assignment planner

**Files:**
- Create: `apps/api/core/radio/failover.py`
- Create: `tests/test_radio_failover.py`

**Interfaces:**
- Produces `ChannelTarget(channel_kind: str, frequency_hz: int, mode: str)`.
- Produces `ChannelPlan(target: ChannelTarget, desired_replicas: int, active: tuple[ReceiverDescriptor, ...], standby: tuple[ReceiverDescriptor, ...])`.
- Produces `channel_target_for(descriptor: ReceiverDescriptor) -> ChannelTarget | None`.
- Produces `build_channel_plans(descriptors: Iterable[ReceiverDescriptor], desired_replicas: int) -> tuple[ChannelPlan, ...]`.

- [ ] **Step 1: Write RED planner tests**

Cover deterministic grouping, configuration order, desired replica slicing, and duplicate-lineage suppression. A descriptor without frequency/mode returns no managed target.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=apps/api /home/ubuntu/seacommons/apps/api/.venv/bin/pytest -q tests/test_radio_failover.py`
Expected: import failure because `core.radio.failover` does not exist.

- [ ] **Step 3: Implement minimal pure planner**

Use frozen dataclasses. Validate channel kind against `dsc|navtex|monitor`, positive frequency, non-empty lowercase mode, and replica range 1–8. Deduplicate `physical_lineage` globally before channel slicing.

- [ ] **Step 4: Run GREEN**

Run the Task 1 test plus `tests/test_remote_receiver_registry.py`.

- [ ] **Step 5: Commit**

Commit message: `feat: plan bounded radio channel assignments`.

### Task 2: Managed runtime active/standby failover

**Files:**
- Modify: `apps/api/core/radio/runtime.py`
- Modify: `tests/test_radio_runtime.py`
- Test: `tests/test_radio_failover.py`

**Interfaces:**
- Extend `RemoteRadioRuntime(..., failover_enabled: bool=False, channel_replicas: int=3, stale_after_s: float=30.0, retry_after_s: float=120.0, monotonic_clock=time.monotonic, utcnow=...)`.
- Managed receiver states are process-local: `active`, `standby`, `cooldown`.
- `status(include_receivers=True)` keeps `state="connected"` for healthy active receivers so Listen Live eligibility remains compatible; standby/cooldown rows use those literal states.
- `status()` adds bounded `channels` summaries.

- [ ] **Step 1: Write RED runtime tests**

Add tests proving: managed mode starts only 3 of 5 ranked candidates; hard disconnect promotes candidate 4; a recovered rank-1 receiver does not eager-failback; a failed promotion tries candidate 5; stale connected receiver fails over after the stale threshold; cooldown receiver is retryable only after retry time; legacy mode still starts all candidates.

- [ ] **Step 2: Run RED**

Run the new managed-runtime tests and confirm constructor/status failures are due to absent failover behavior.

- [ ] **Step 3: Implement managed lifecycle**

Create adapter objects for all managed candidates but start only planned active entries. On supervisor pass, inspect active health, move unhealthy entries to cooldown, fill deficits from ranked standby, and later make expired cooldown entries eligible without eager failback.

- [ ] **Step 4: Run GREEN**

Run `tests/test_radio_runtime.py tests/test_radio_failover.py tests/test_radio_live_listen.py tests/test_radio_burst_engine.py`.

- [ ] **Step 5: Commit**

Commit message: `feat: fail over radio receivers by channel`.

### Task 3: Channel-aware ranked public pool and config

**Files:**
- Modify: `apps/api/core/radio/public_pool.py`
- Modify: `apps/api/core/radio/catalog_store.py`
- Modify: `apps/api/core/radio/runtime.py`
- Modify: `apps/api/core/config.py`
- Modify: `tests/test_radio_runtime.py`
- Modify: `tests/test_receiver_catalog_persistence.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Extend `rank_persistent_catalog(..., channel_kind: str="monitor")` so returned descriptors preserve the requested target kind.
- Extend `public_receiver_pool(targets: Iterable[ChannelTarget] | None=None, limit: int=16)`; omitted targets preserve the existing 2187.5 kHz USB monitor bootstrap.
- `start_remote_radio_from_config()` passes configured explicit targets into the public pool and the four failover settings into `RemoteRadioRuntime`.

- [ ] **Step 1: Write RED pool/config tests**

Prove DSC and NAVTEX targets receive compatible ranked descriptors with the requested kind/frequency/mode, total pool remains bounded, and config defaults match the spec.

- [ ] **Step 2: Run RED**

Run focused catalog/runtime/config tests and observe signature/default failures.

- [ ] **Step 3: Implement minimal target-aware pool**

Reuse `rank_persistent_catalog`; never duplicate the persistent score formula. Deduplicate physical lineage globally and cap the final returned pool to `limit`.

- [ ] **Step 4: Run GREEN**

Run catalog persistence, receiver catalog, radio runtime and config tests.

- [ ] **Step 5: Commit**

Commit message: `feat: rank standby receivers per radio channel`.

### Task 4: Public-safe coverage status and bounded metrics

**Files:**
- Modify: `apps/api/core/acquisition/status.py`
- Modify: `apps/api/core/radio/bridge.py`
- Modify: `apps/api/core/observability.py`
- Modify: `tests/test_live_pipeline_status.py`
- Modify: `tests/test_observability.py`

**Interfaces:**
- Radio status adds `channels: list[dict]`, max 8 rows.
- Allowed channel fields are exactly `channel_kind`, `frequency_hz`, `mode`, `desired`, `active`, `standby`, `cooldown`, `failovers`.
- Remote-radio metric outcomes add `reconnected`, `reconnect_failed`, `failover`, `standby_promoted`, `cooldown_retry`.

- [ ] **Step 1: Write RED privacy/status tests**

Assert `/api/v1/live/pipeline` exposes bounded channel coverage while excluding `frontend_url`, `source_terms`, `physical_lineage`, session IDs and error text. Add metric-cardinality tests for the new outcomes.

- [ ] **Step 2: Run RED**

Run pipeline/observability tests and confirm missing `channels` or outcome normalization failures.

- [ ] **Step 3: Implement sanitizer and metric updates**

Pass runtime channel aggregates through `radio_acquisition_status()` and whitelist only the defined public fields.

- [ ] **Step 4: Run GREEN**

Run `tests/test_live_pipeline_status.py tests/test_observability.py tests/test_radio_runtime.py tests/test_public_policy.py`.

- [ ] **Step 5: Commit**

Commit message: `feat: expose bounded radio failover coverage`.

### Task 5: Release gate, production activation and controlled smoke

**Files:**
- Modify: `docs/current_work.md`
- Modify: `prompt.md`
- Modify: `docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md`
- Modify: this plan execution record.
- Production-only ignored config: `apps/api/.env`.

- [ ] **Step 1: Run focused Packet G gate**

Run all radio runtime/catalog/listen/burst/pipeline/observability tests, Ruff on touched backend modules, and `git diff --check`.

- [ ] **Step 2: Run full release gate**

Run full backend pytest, canonical Ruff/mypy/migration/dependency gates, web tests/lint/build, edge tests/dry-run, and exact diff review.

- [ ] **Step 3: Merge/push exact green commit**

Push the reviewed branch, integrate into `main`, and wait for Full CI/CodeQL/Federated Live/Alarm Phone lifecycle success.

- [ ] **Step 4: Activate failover on VM**

Set `REMOTE_RADIO_FAILOVER_ENABLED=true`, `REMOTE_RADIO_CHANNEL_REPLICAS=3`, `REMOTE_RADIO_FAILOVER_STALE_S=30`, `REMOTE_RADIO_FAILOVER_RETRY_S=120` in ignored runtime config. Keep `AUDIO_EVIDENCE_ENABLED=false`. Restart the API service.

- [ ] **Step 5: Controlled production smoke**

Verify `/health`, `/ready`, `/api/v1/live/pipeline`, receiver mesh and Listen Live. Record initial active/standby counts. Perform a reversible controlled receiver failure only if it can be isolated without terminating the API; otherwise exercise the exact production-config runtime against real candidate descriptors in a bounded diagnostic process. Confirm a standby promotion and restored replica count.

- [ ] **Step 6: Record release evidence**

Update controllers with deployed SHA, active/standby/failover counts, public privacy scan, CI results and rollback flag.

- [ ] **Step 7: Commit release record**

Commit message: `docs: close radio coverage auto failover`.

## Final acceptance gate

Packet G is complete only when three independent lineages remain active for the production target when capacity exists, a failed active receiver is replaced by ranked standby without eager failback, Listen Live follows currently active receivers, public status leaks no private receiver fields, all blocking local/remote gates are green, and rollback by disabling managed failover is verified.
