# Live Humanitarian/Maritime + Unified Acquisition Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace legacy Live grouping with canonical Humanitarian/Maritime compartments and make AIS, radio, first-party/public feeds, partner inputs and future connectors participate in one shared acquisition -> observation -> evidence pipeline with public-safe provenance.

**Architecture:** Backend remains authoritative for domain/publication. Existing source-specific adapters normalize into shared observation/evidence contracts and expose health through one acquisition-status model. Radio is only one adapter family inside that pipeline; Live consumes canonical `humanitarian | maritime | all` modes and never uses acquisition source as a top-level content category.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, pytest, Prometheus metrics, React/Vite, Node test runner, systemd production services.

**Spec:** `docs/superpowers/specs/2026-09-07-live-humanitarian-maritime-acquisition-pipeline-design.md`

## Global Constraints

- Public Live primary compartments are exactly `humanitarian` and `maritime`; `all` is their union.
- `security` may be accepted as a temporary backend alias but must not be emitted as the canonical UI label/count.
- Safety and Maritime Intelligence retain separate backend publication gates even though both render under Maritime.
- Radio receiver descriptors must be `enabled`, `terms_status=allowed`, and have explicit `source_terms` before runtime start.
- Multiple frontends for one physical receiver remain one evidence lineage.
- Raw RF/audio is never treated as decoded DSC/NAVTEX.
- `AUDIO_EVIDENCE_ENABLED` remains false throughout this plan unless separately authorized.
- Humanitarian public surfaces never expose MMSI/IMO/callsign/tracker dossier data.
- Every behavior change follows TDD RED -> GREEN and one semantic commit per task.

---

## File map

Backend responsibilities:

- `apps/api/core/live/feed.py` — canonical public `humanitarian | maritime | all` composition/counts.
- `apps/api/core/api/routes/live.py` — Live mode API + new public-safe pipeline endpoint.
- `apps/api/core/acquisition/status.py` — shared bounded acquisition-status contract across AIS, radio, first-party/public feeds and partner inputs.
- `apps/api/core/radio/bridge.py` — radio adapter bridge into existing structured evidence ingestion; no separate pipeline controller.
- `apps/api/core/radio/runtime.py` — receiver adapter lifecycle and detailed safe health snapshot.
- `apps/api/core/radio/registry.py` — channel/public-label descriptor fields and validation.
- `apps/api/core/radio/structured_runtime.py` — shared structured runtime instance/status.
- `apps/api/core/radio/source_observation.py` / `structured_source_observation.py` — canonical persistence remains unchanged unless a missing reference accessor is required.
- `apps/api/core/evidence/cross_modal.py` — consume canonical structured-radio evidence references only if current evidence-class mapping is incomplete.
- `apps/api/core/bootstrap.py` — start exactly one radio evidence pipeline.
- `apps/api/core/config.py` — bounded receiver/channel config only; audio stays disabled.

Frontend responsibilities:

- `apps/web/src/main.jsx` — Humanitarian/Maritime macros, Safety labels, provenance/pipeline UI.
- `apps/web/src/hooks/useLiveFeed.js` — canonical `maritime` mode/count handling and pipeline polling.
- `apps/web/src/features/live/feedStatus.js` — canonical total/count helpers.
- `apps/web/src/status/StatusApp.jsx` — Humanitarian/Maritime status copy.
- `apps/web/src/features/live/*test.js` and relevant component tests — semantic/UI regression coverage.

---

### Task 1: Canonical public Humanitarian/Maritime feed contract

**Files:**
- Modify: `apps/api/core/live/feed.py`
- Modify: `apps/api/core/api/routes/live.py`
- Test: `tests/test_live_feed.py`
- Test: `tests/test_live_compartments.py`

**Interfaces:**
- Consumes: existing `compartment_for_domain()`, `domains_for_mode()`, `_public_intel_feature()`.
- Produces: `public_signal_collection(..., mode="maritime")`; `meta.mode_counts={"humanitarian": int, "maritime": int}`; optional `meta.domain_counts` detail.

- [ ] **Step 1: Write RED tests for canonical modes**

Add tests asserting: `mode=maritime` contains public Safety plus explicitly published Maritime Intelligence; `mode=humanitarian` excludes both; `mode=all` is the union; `security` alias returns the same feature IDs as `maritime`; canonical `mode_counts` has no `security` key.

- [ ] **Step 2: Run RED**

Run:
```bash
export PYTHONPATH="$PWD/apps/api:$PWD"
PY=/home/ubuntu/seacommons/apps/api/.venv/bin/python3
$PY -m pytest -q tests/test_live_feed.py tests/test_live_compartments.py -k 'maritime or mode_counts or security_alias'
```
Expected: failures because `maritime` is not an accepted route mode and counts are still split `security/safety`.

- [ ] **Step 3: Implement minimal backend grouping**

In `public_signal_collection()`, keep internal buckets `humanitarian/security/safety`, then expose `maritime = safety + security` after each bucket has independently passed its current projector/gates. Preserve ordering/caps and never merge security eligibility into Safety eligibility.

Update route pattern to `^(humanitarian|maritime|security|all)$`; normalize `security -> maritime` before calling the feed.

- [ ] **Step 4: GREEN + privacy/publication regression**

Run:
```bash
$PY -m pytest -q tests/test_live_feed.py tests/test_live_compartments.py tests/test_publication_policy.py tests/test_publication_policy.py
```
Expected: all pass; no previously internal Security correlated alert becomes public.

- [ ] **Step 5: Commit**

```bash
git add apps/api/core/live/feed.py apps/api/core/api/routes/live.py tests/test_live_feed.py tests/test_live_compartments.py
git commit -m "feat: expose canonical maritime live compartment"
```

### Task 2: Normalize Maritime Safety labels and provenance

**Files:**
- Modify: `apps/api/core/live/projection.py`
- Modify: `apps/api/core/domain/visual_category.py` only if canonical label mapping belongs there
- Test: `tests/test_live_feed.py`
- Test: `tests/test_visual_category.py`

**Interfaces:**
- Consumes: existing `ais_nav_status_kind`, `event.type`, `maritime_domain`.
- Produces: public properties `operational_label` and `input_modality`; labels include `Aground`, `Not Under Command`, `Restricted Manoeuvrability`, `DSC distress`, and safe fallback `Maritime safety`.

- [ ] **Step 1: Write RED Safety-label tests**

Create table-driven tests for `aground`, `not_under_command`, and `restricted_manoeuvrability`. Assert primary operational label is semantic, while source remains separate provenance. Add a Humanitarian test proving MMSI/IMO/callsign remain absent.

- [ ] **Step 2: Run RED**

```bash
$PY -m pytest -q tests/test_live_feed.py tests/test_visual_category.py -k 'operational_label or aground or manoeuvrability or input_modality'
```
Expected: missing properties/incorrect legacy grouping.

- [ ] **Step 3: Implement minimal mapping**

Add a bounded pure helper mapping canonical Safety status -> display label and source family -> `input_modality`. Do not derive Humanitarian/Maritime membership in React.

- [ ] **Step 4: GREEN**

```bash
$PY -m pytest -q tests/test_live_feed.py tests/test_visual_category.py tests/test_publication_policy.py
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/core/live/projection.py apps/api/core/domain/visual_category.py tests/test_live_feed.py tests/test_visual_category.py
git commit -m "feat: label maritime safety observations canonically"
```

### Task 3: Extend receiver descriptors with explicit channel purpose and public station label

**Files:**
- Modify: `apps/api/core/radio/registry.py`
- Test: `tests/test_radio_runtime.py`

**Interfaces:**
- Produces descriptor fields: `public_label: str`, `channel_kind: Literal["dsc","navtex","monitor"]`, `frequency_hz: int | None`, `mode: str | None`.
- Existing `physical_lineage`, terms, capabilities and receiver ID semantics remain unchanged.

- [ ] **Step 1: RED validation tests**

Test allowed channel kinds, public-label length/normalization, frequency must lie inside at least one receiver capability when provided, `dsc/navtex` require frequency, and descriptors with blocked/unknown terms remain non-runnable.

- [ ] **Step 2: Run RED**

```bash
$PY -m pytest -q tests/test_radio_runtime.py
```
Expected: constructor does not accept channel/public-label fields.

- [ ] **Step 3: Implement minimal descriptor extension**

Keep config backward-compatible: descriptors without `channel_kind` default to `monitor`; `public_label` defaults to `receiver_id`; do not expose `frontend_url` through public serializers.

- [ ] **Step 4: GREEN**

```bash
$PY -m pytest -q tests/test_radio_runtime.py tests/test_radio_runtime.py
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/core/radio/registry.py tests/test_radio_runtime.py tests/test_radio_runtime.py
git commit -m "feat: describe radio channels and public station labels"
```

### Task 4: Integrate radio adapters into the unified acquisition/evidence pipeline

**Files:**
- Create: `apps/api/core/radio/bridge.py`
- Create: `apps/api/core/acquisition/status.py`
- Modify: `apps/api/core/radio/provider.py`
- Modify: `apps/api/core/radio/runtime.py`
- Modify: `apps/api/core/radio/structured_runtime.py`
- Modify: `apps/api/core/bootstrap.py`
- Create: `tests/test_acquisition_radio_bridge.py`
- Test: `tests/test_radio_runtime.py`
- Test: `tests/test_structured_radio_runtime.py`

**Interfaces:**
- Produces: `handle_radio_observation(observation: RadioObservation) -> None`, `handle_decoded_radio_message(message: DecodedRadioMessage) -> dict[str, object]`, and a radio acquisition-health adapter registered in the shared acquisition-status registry.
- `handle_radio_observation()` persists canonical radio observations through the existing source-observation path; it does not own a separate runtime or truth store.
- Structured routing occurs only for explicitly decoded payloads delivered through `DecodedRadioMessage(kind: Literal["dsc","navtex"], receiver_id: str, provider: str, physical_lineage: str, frequency_hz: int, mode: str, observed_at: datetime, payload: Mapping[str, Any] | str, provider_message_id: str | None = None)` defined in `core.radio.provider`; ordinary signal-level `RadioObservation` remains monitor-only.

- [ ] **Step 1: RED orchestration tests**

Test disabled no-op; terms-allowed receiver start; physical-lineage dedup; observation persistence; monitor observation does not invoke DSC/NAVTEX; decoded DSC invokes shared structured runtime once; decoded NAVTEX invokes it once; replay does not duplicate canonical observation; status reports receiver/channel state without URL/session/source-terms fields.

- [ ] **Step 2: Run RED**

```bash
$PY -m pytest -q tests/test_acquisition_radio_bridge.py tests/test_radio_runtime.py tests/test_structured_radio_runtime.py
```
Expected: acquisition bridge/status contract missing.

- [ ] **Step 3: Implement the radio acquisition bridge**

Keep the existing receiver runtime as an acquisition adapter. Add a thin bridge from explicit decoded radio messages into the shared `StructuredRadioRuntime`; register radio health in the unified acquisition-status registry. Radio must remain an adapter feeding the shared acquisition/evidence path and existing publication gates.

Adapters must distinguish signal observations from decoded structured messages. If current Kiwi/OpenWebRX transports do not emit decoded messages, they remain monitor-only until a decoder output is available; do not parse arbitrary audio text.

- [ ] **Step 4: GREEN + persistence regressions**

```bash
$PY -m pytest -q tests/test_acquisition_radio_bridge.py tests/test_radio_runtime.py tests/test_structured_radio_runtime.py tests/test_radio_source_observation.py tests/test_structured_radio_source_observation.py
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/core/acquisition/status.py apps/api/core/radio/bridge.py apps/api/core/radio/provider.py apps/api/core/radio/runtime.py apps/api/core/radio/structured_runtime.py apps/api/core/bootstrap.py tests/test_acquisition_radio_bridge.py tests/test_radio_runtime.py tests/test_structured_radio_runtime.py
git commit -m "feat: integrate radio into acquisition evidence pipeline"
```

### Task 5: Connect structured radio evidence to cross-modal references

**Files:**
- Modify: `apps/api/core/evidence/cross_modal.py` only if class/ref helpers are incomplete
- Create or modify: `apps/api/core/radio/evidence_bridge.py`
- Test: `tests/test_radio_cross_modal_bridge.py`
- Test: `tests/test_cross_modal_evidence_contracts.py`

**Interfaces:**
- Produces: `evidence_reference_for_dsc(...) -> EvidenceReference`, `evidence_reference_for_navtex(...) -> EvidenceReference`.
- DSC uses evidence class `dsc_message`, NAVTEX uses `navtex_message`, modality `radio`, source lineage = physical receiver lineage.

- [ ] **Step 1: RED lineage tests**

Assert two provider frontends with the same physical receiver collapse to one independence key; DSC and NAVTEX from distinct physical receivers can form distinct source groups; derived decoder output never adds another group beyond its physical receiver.

- [ ] **Step 2: Run RED**

```bash
$PY -m pytest -q tests/test_radio_cross_modal_bridge.py tests/test_cross_modal_evidence_contracts.py
```

- [ ] **Step 3: Implement reference bridge only**

Do not mutate ResolutionAssessment, MaritimeEpisode, hypothesis state, or publication from this bridge. It only creates canonical evidence references consumed by existing packet builders.

- [ ] **Step 4: GREEN**

```bash
$PY -m pytest -q tests/test_radio_cross_modal_bridge.py tests/test_cross_modal_evidence_contracts.py tests/test_cross_modal_independence.py
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/core/radio/evidence_bridge.py apps/api/core/evidence/cross_modal.py tests/test_radio_cross_modal_bridge.py tests/test_cross_modal_evidence_contracts.py
git commit -m "feat: bridge structured radio into cross-modal evidence"
```

### Task 6: Add unified public-safe acquisition status endpoint

**Files:**
- Modify: `apps/api/core/api/routes/live.py`
- Create: `apps/api/core/acquisition/status.py`
- Test: `tests/test_live_pipeline_status.py`

**Interfaces:**
- Produces `GET /api/v1/live/pipeline` with:
```json
{
  "generated_at": "...",
  "sources": [
    {"family":"ais","state":"live|degraded|offline","label":"AIS"},
    {"family":"first_party","state":"live|degraded|offline","label":"First-party feeds"},
    {"family":"public_feed","state":"live|degraded|offline","label":"Public feeds"},
    {"family":"radio","state":"live|degraded|offline|disabled","label":"Radio","receivers":[]}
  ]
}
```

- [ ] **Step 1: RED privacy/shape tests**

Assert endpoint is public, bounded, and contains none of: `frontend_url`, `source_terms`, `session_id`, credentials, raw payload, transcript/audio body, MMSI/IMO/callsign.

- [ ] **Step 2: Run RED**

```bash
$PY -m pytest -q tests/test_live_pipeline_status.py
```
Expected: 404/missing contract.

- [ ] **Step 3: Implement endpoint**

Build one bounded status snapshot from existing in-memory health for AIS, source registries/connectors and radio. No expensive DB scan. Cap any source-specific detail, including radio receivers, to configured bounds.

- [ ] **Step 4: GREEN**

```bash
$PY -m pytest -q tests/test_live_pipeline_status.py tests/test_pilot_smoke.py tests/test_live_feed.py
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/core/api/routes/live.py apps/api/core/acquisition/status.py tests/test_live_pipeline_status.py
git commit -m "feat: expose public-safe live acquisition pipeline status"
```

### Task 7: Refactor Live UI to Humanitarian / Maritime and integrate pipeline provenance

**Files:**
- Modify: `apps/web/src/main.jsx`
- Modify: `apps/web/src/hooks/useLiveFeed.js`
- Modify: `apps/web/src/features/live/feedStatus.js`
- Modify: `apps/web/src/status/StatusApp.jsx`
- Create: `apps/web/src/features/live/pipelineStatus.js`
- Test: `apps/web/src/features/live/feedStatus.test.js`
- Create: `apps/web/src/features/live/pipelineStatus.test.js`
- Modify relevant existing Live component tests.

**Interfaces:**
- UI consumes `mode_counts.humanitarian`, `mode_counts.maritime`, `properties.operational_label`, `properties.input_modality`, and `/api/v1/live/pipeline`.
- UI never computes publication eligibility.

- [ ] **Step 1: RED UI semantic tests**

Add tests asserting no rendered primary labels `PUBLIC FEEDS`, `DIRECT`, or `Maritime Security`; macros are `Humanitarian` and `Maritime`; `liveSignalTotal()` sums only canonical public counts; Safety items are nested under Maritime; Aground/NUC/restricted manoeuvrability labels are preserved; acquisition health renders AIS, first-party/public feeds, partner inputs and radio in one source-status area; none becomes a third signal category.

- [ ] **Step 2: Run RED**

```bash
cd apps/web
npm test -- --runInBand
```
Expected: macro/count/pipeline tests fail against current UI.

- [ ] **Step 3: Implement UI refactor**

Change `SIGNALS_MACRO_GROUPS` to `humanitarian` and `maritime`. Move vessel Safety categories under Maritime. Remove Security-specific `other` handling from public copy; use backend operational labels/provenance. Poll `/api/v1/live/pipeline` on the same bounded cadence as feed status and render compact acquisition health in the existing Live sidebar.

- [ ] **Step 4: GREEN + build**

```bash
npm test
npm run lint
npm run build
npm audit --omit=dev --audit-level=high
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/main.jsx apps/web/src/hooks/useLiveFeed.js apps/web/src/features/live/feedStatus.js apps/web/src/features/live/pipelineStatus.js apps/web/src/status/StatusApp.jsx apps/web/src/features/live/*.test.js
git commit -m "feat: unify live ui around humanitarian and maritime data"
```

### Task 8: Unified acquisition rollout, receiver activation and production verification

**Files:**
- Modify: deployment receiver config file referenced by `REMOTE_RADIO_RECEIVERS_FILE` (do not commit secrets/private URLs if repository policy forbids it)
- Modify: `docs/current_work.md`
- Modify: `prompt.md`
- Modify: `docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md`
- Update this plan execution record.

**Interfaces:**
- Runtime flags: `STRUCTURED_RADIO_ENABLED`, `REMOTE_RADIO_ENABLED`; keep `AUDIO_EVIDENCE_ENABLED=false`.

- [ ] **Step 1: Pre-activation release gate**

Run from repo root:
```bash
export PYTHONPATH="$PWD/apps/api:$PWD"
PY=/home/ubuntu/seacommons/apps/api/.venv/bin/python3
$PY -m pytest -q
(cd apps/api && $PY -m ruff check core tests --select E9,F63,F7,F82)
(cd apps/api && $PY -m mypy core/domain/live_contracts.py core/live/projection.py core/intel/public_policy.py core/intel/public_geometry.py --follow-imports=skip)
(cd apps/api && $PY -m pip_audit . --strict)
(cd apps/web && npm test && npm run lint && npm run build && npm audit --omit=dev --audit-level=high)
(cd apps/edge && npm test && npx wrangler deploy --dry-run && npm audit --omit=dev --audit-level=high)
git diff --check
```
Expected: all blocking gates green.

- [ ] **Step 2: Configure terms-allowed receivers only**

For each receiver, require explicit provider, public label, frontend URL, physical lineage, capability range/modes, `source_terms`, `terms_status=allowed`, channel kind, and frequency. Start with a bounded set (1–3 receivers), preferably one physical receiver per frontend lineage.

- [ ] **Step 3: Enable structured runtime first**

Set `STRUCTURED_RADIO_ENABLED=true`, `REMOTE_RADIO_ENABLED=false`, restart API/worker, and verify `/api/v1/live/pipeline` reports structured capability without remote receivers. Feed behavior must remain unchanged.

- [ ] **Step 4: Enable remote receiver runtime**

Set `REMOTE_RADIO_ENABLED=true`, keep `AUDIO_EVIDENCE_ENABLED=false`, restart supervised services. Verify the unified acquisition snapshot remains green for existing AIS/first-party/public sources and includes truthful radio configured/started/failed counts, station labels, channel/frequency and last observation timestamps.

- [ ] **Step 5: End-to-end smoke**

Verify:
```text
receiver connected
→ RadioObservation persisted
→ decoded DSC/NAVTEX fixture or real decoded provider message accepted
→ structured SourceObservation persisted
→ cross-modal EvidenceReference has radio modality + physical lineage
→ Safety/context projection obeys existing gate
→ /api/v1/live/signals?mode=maritime contains only public-eligible output
→ /api/v1/live/pipeline shows all active acquisition families and public-safe radio receiver/channel provenance
→ Humanitarian privacy scan = 0 MMSI/IMO/callsign leaks
```

Do not fabricate a real DSC/NAVTEX message if no receiver currently supplies decoded output; in that case production can truthfully show receiver `live` + `monitor` channel while structured integration is verified with the canonical decoder fixture until a decoded source is configured.

- [ ] **Step 6: CI + public host verification**

Push to `main`, wait for Full CI/CodeQL/Alarm Phone lifecycle as applicable. Verify `https://live.seacommons.org` displays Humanitarian/Maritime macros and acquisition pipeline status; `mode=maritime` is HTTP 200; no internal Security alert is exposed.

- [ ] **Step 7: Update controllers and commit release record**

Record deployed SHA, production schema `0023_review_records`, radio receiver count, channel types, runtime flags, public smoke results, and rollback flags. Remove stale claims that Evidence Fusion remains isolated from production.

Commit:
```bash
git add docs/current_work.md prompt.md docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md docs/superpowers/plans/2026-09-07-live-humanitarian-maritime-acquisition-pipeline.md
git commit -m "docs: record unified acquisition rollout"
```

## Final acceptance gate

The packet is complete only when all of the following are simultaneously true:

1. Backend full suite + canonical static/dependency gates green.
2. Web + edge tests/lint/build/audit green.
3. Public Live UI shows **Humanitarian** and **Maritime**, not PUBLIC FEEDS/DIRECT/Maritime Security.
4. Aground/NUC/restricted manoeuvrability are visibly Maritime Safety.
5. `/api/v1/live/pipeline` represents all acquisition families with bounded public-safe metadata; radio receiver/channel fields are only source-specific provenance.
6. Existing AIS/first-party/public acquisition health remains truthful, and at least one terms-allowed receiver is either `live` or truthfully `degraded/offline` with no fake connectivity state.
7. Structured DSC/NAVTEX path is proven end-to-end with real decoded input or canonical decoder fixture; no raw audio is mislabeled as decoded evidence.
8. Cross-modal independence uses physical receiver lineage.
9. `AUDIO_EVIDENCE_ENABLED=false` unless separately authorized.
10. Humanitarian privacy and Security publication regressions remain green.
