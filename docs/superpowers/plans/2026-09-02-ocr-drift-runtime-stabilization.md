# OCR and Drift Runtime Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Alarm Phone image extraction observable and independent of text classification, while making operational Drift consume only verified locations and honestly describe marine forcing.

**Architecture:** Add typed media/image diagnostic boundaries without changing public semantics by default. Add per-variable forcing provenance and derive quality from successful samples, then project only eligible results.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, EasyOCR, Tesseract, Pillow, NumPy, OpenDrift, Copernicus Marine, pytest.

**Spec:** `docs/superpowers/specs/2026-09-02-ocr-drift-runtime-stabilization-design.md`

## Global Constraints

- Preserve public semantics unless an explicit V2 enable flag is set.
- Never log raw OCR text, image payloads, cookies, secrets, or authorization data.
- Do not mutate production rows or external infrastructure during implementation.
- Every production-code behavior change starts with a failing regression test.
- Drift eligibility is never bypassed by `force=True`.

---

### Task 1: Establish the project test command

**Files:**
- Modify: none

**Interfaces:**
- Consumes: `apps/api/pyproject.toml` development dependencies.
- Produces: a repeatable pytest command for all later tasks.

- [ ] **Step 1: Inspect the documented environment/bootstrap commands**

Run `rg -n "uv sync|pytest|dependency-groups|optional-dependencies" apps/api/pyproject.toml docs/DEVELOPMENT.md docs/TESTING.md`.

- [ ] **Step 2: Install only declared development dependencies if absent**

Use the repository's documented `uv sync` command; do not install undeclared packages individually.

- [ ] **Step 3: Prove collection works**

Run `PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest --collect-only -q tests/test_geoextract.py` and require exit 0.

### Task 2: Canonical X media resolver

**Files:**
- Create: `apps/api/core/intel/x_media.py`
- Modify: `apps/api/core/intel/twikit_monitor.py`
- Modify: `apps/api/core/intel/backfill_alarm_phone.py`
- Test: `tests/test_x_media.py`

**Interfaces:**
- Consumes: Twikit tweet objects and `fetch_tweet_photos(tweet_id)`.
- Produces: `resolve_x_media(tweet, tweet_id, quoted_tweet=None) -> XMediaResolution`.

- [ ] **Step 1: Write failing tests** for all live shapes, continued fallback search after an invalid earlier URL, own/quoted syndication, deduplication, allow-list rejection, and `pbs.twimg.com` original-resolution normalization.
- [ ] **Step 2: Run `python -m pytest tests/test_x_media.py -q`** and confirm failures are missing-interface/behavior failures.
- [ ] **Step 3: Implement immutable `XMediaItem` and `XMediaResolution` types plus the minimal resolver.**
- [ ] **Step 4: Replace live and backfill URL discovery with the resolver while retaining compatibility wrappers.**
- [ ] **Step 5: Run media and Twikit tests** and require exit 0.

### Task 3: Structured image extraction diagnostics

**Files:**
- Create: `apps/api/core/intel/image_extraction.py`
- Modify: `apps/api/core/intel/x_media_utils.py`
- Modify: `apps/api/core/intel/map_pin_geolocate.py`
- Test: `tests/test_image_extraction.py`
- Test: `tests/fixtures/ocr/README.md`

**Interfaces:**
- Consumes: resolved image URL and OCR adapters.
- Produces: `extract_image(url) -> ImageExtractionResult` and compatibility `_ocr_photo()` output.

- [ ] **Step 1: Add privacy-safe failing tests** distinguishing download failure, no text, parser rejection, Tesseract candidate, popup/no-popup, pin/no-pin, and insufficient landmarks without retaining raw text.
- [ ] **Step 2: Run the new tests and confirm expected failures.**
- [ ] **Step 3: Implement typed candidates/results and refactor existing stages to populate them.**
- [ ] **Step 4: Keep `_ocr_photo()` as a projection of the structured result so existing callers remain stable.**
- [ ] **Step 5: Run image, parser, media, location-evidence, and Twikit tests.**

### Task 4: Parser candidates and OCR consensus

**Files:**
- Modify: `apps/api/core/intel/geoextract.py`
- Modify: `apps/api/core/intel/image_extraction.py`
- Test: `tests/test_geoextract.py`
- Test: `tests/test_image_extraction.py`

**Interfaces:**
- Consumes: transient OCR text.
- Produces: all `ParsedCoordinateCandidate` records and the existing best-coordinate compatibility API.

- [ ] **Step 1: Add failing regressions** for missing degree/prime glyphs, suffix DMM, labelled decimal coordinates, invalid ranges, and conflicting candidates.
- [ ] **Step 2: Confirm failures are parser coverage failures.**
- [ ] **Step 3: Implement candidate parsing with matched-format and validation metadata.**
- [ ] **Step 4: Preserve geodesic consensus and ensure single-engine/disputed results remain unverified.**
- [ ] **Step 5: Run parser/OCR/location suites.**

### Task 5: OCR eligibility shadow mode and queue retry state

**Files:**
- Modify: `apps/api/core/config.py`
- Modify: `apps/api/core/intel/twikit_monitor.py`
- Modify: `apps/api/core/intel/media_ocr_queue.py`
- Modify: `apps/api/core/observability.py`
- Test: `tests/test_twikit_monitor.py`
- Test: `tests/test_media_ocr_queue.py`

**Interfaces:**
- Consumes: `ALARM_PHONE_IMAGE_V2_ENABLED` and `ALARM_PHONE_IMAGE_V2_SHADOW`.
- Produces: independent image-analysis eligibility with unchanged public output in shadow mode.

- [ ] **Step 1: Add failing tests** proving a non-distress Alarm Phone image is analyzed in shadow mode but does not alter classification, publication, coordinate, notification, or Drift.
- [ ] **Step 2: Add a failing queue test** proving overflow remains retryable rather than terminally dropped.
- [ ] **Step 3: Implement flags, shadow scheduling, privacy-safe metrics, and retry state.**
- [ ] **Step 4: Run Twikit, queue, Live policy, and auto-Drift tests.**

### Task 6: Unified verified LocationEvidence gate

**Files:**
- Modify: `apps/api/core/intel/location_evidence.py`
- Modify: `apps/api/core/intel/drift_service.py`
- Modify: `apps/api/core/api/routes/intel.py`
- Modify: `apps/api/core/intel/backfill_alarm_phone.py`
- Test: `tests/test_location_evidence.py`
- Test: `tests/test_auto_drift_eligibility.py`
- Test: `tests/test_intel_auto_drift_route.py`

**Interfaces:**
- Consumes: structured extraction result and stored canonical event state.
- Produces: one `is_auto_drift_eligible(event)` decision for every Drift entry path.

- [ ] **Step 1: Add failing tests** for single-engine, disputed, invalid-region, land, stale/resolved, forced, manual-route, and backfill rejection.
- [ ] **Step 2: Confirm each test fails at the intended bypass.**
- [ ] **Step 3: Implement evidence comparison and route every Drift origin through the shared gate.**
- [ ] **Step 4: Run all location, Drift eligibility, backfill, and Live tests.**

### Task 7: Correct CMEMS depth selection

**Files:**
- Modify: `apps/api/core/ocean/cmems.py`
- Modify: `apps/api/core/drift/opendrift_pool.py`
- Test: `tests/test_cmems.py`

**Interfaces:**
- Consumes: provider dataset depth coordinates.
- Produces: selected surface depth and selection-method metadata without out-of-range requests.

- [ ] **Step 1: Add fake-client failing tests** with shallowest depths `0.494` and `1.5` metres, asserting no hardcoded `[0.0, 1.0]` request.
- [ ] **Step 2: Confirm the current calls fail those assertions.**
- [ ] **Step 3: Implement nearest/metadata-derived surface-depth selection and return selected depth provenance.**
- [ ] **Step 4: Run CMEMS and area-extraction tests.**

### Task 8: Per-variable forcing provenance and honest quality

**Files:**
- Create: `apps/api/core/drift/forcing.py`
- Modify: `apps/api/core/drift/cache.py`
- Modify: `apps/api/core/drift/engine.py`
- Modify: `apps/api/core/drift/opendrift_pool.py`
- Test: `tests/test_drift_forcing.py`
- Test: `tests/test_drift_trajectory.py`

**Interfaces:**
- Consumes: CMEMS/Open-Meteo responses and calculated vectors.
- Produces: `ForcingObservation`, grid coverage, per-variable provenance, and conservative quality.

- [ ] **Step 1: Add failing tests** for fetched/calculated/interpolated/cached/fallback derivations and full/partial/zero provider coverage.
- [ ] **Step 2: Add a failing regression** proving total grid failure is currently mislabelled spatiotemporal/operational.
- [ ] **Step 3: Implement observations, coverage reports, mixed resolution metadata, and quality classification.**
- [ ] **Step 4: Replace the blocking CMEMS timeout pattern with bounded cleanup and test timeout duration.**
- [ ] **Step 5: Run forcing, trajectory, profile, and runtime-contract tests.**

### Task 9: Live API/UI projection

**Files:**
- Modify: `apps/api/core/live/projection.py`
- Modify: `apps/api/core/rendering/scene.py`
- Modify: frontend files only if the existing types cannot represent provenance
- Test: `tests/test_live_feed.py`
- Test: `tests/test_drift_scene.py`

**Interfaces:**
- Consumes: verified location and forcing metadata.
- Produces: operational-only Live trajectories and accurate forcing labels.

- [ ] **Step 1: Add failing tests** rejecting mixed/degraded/invalid operational projection and distinguishing measured current from calculated Stokes.
- [ ] **Step 2: Implement the minimal projection changes.**
- [ ] **Step 3: Run backend projection tests and, if frontend changes, typecheck/tests/build.**

### Task 10: Full verification and production read-only proof

**Files:**
- Modify: `docs/OCR_AND_DRIFT_PIPELINE_AUDIT_2026-09-02.md`

**Interfaces:**
- Consumes: all implemented tasks.
- Produces: review-ready evidence and an explicit production rollout boundary.

- [ ] **Step 1: Run targeted OCR/parser/media/location suites.**
- [ ] **Step 2: Run targeted CMEMS/forcing/OpenDrift/projection suites.**
- [ ] **Step 3: Run the full backend suite available in the declared development environment.**
- [ ] **Step 4: Run frontend checks only if frontend files changed.**
- [ ] **Step 5: Run read-only API, PostgreSQL, process, package, and journal checks.**
- [ ] **Step 6: Update the audit with confirmed post-change evidence and remaining production rollout actions.**
- [ ] **Step 7: Run `git diff --check` and inspect the final diff/status.**
