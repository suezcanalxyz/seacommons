# OSINT Evidence Pipeline v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct maritime fusion so detector multiplicity is not mislabeled as independent corroboration, and same-lineage AIS indicators cannot auto-open an intelligence case.

**Architecture:** Add a small evidence-lineage layer that resolves every `IntelEvent` to a conservative source/sensor lineage. Fusion keeps emitting compatibility `correlated_alert` records, but computes verification from contributing lineages and treats same-lineage multi-indicator alerts as internal episodes. Public projection hides those internal episodes; independent corroboration remains eligible.

**Tech Stack:** Python 3.12, FastAPI domain code, SQLAlchemy-backed IntelEvent store, pytest, Vite web regression tests.

**Spec:** `docs/superpowers/specs/2026-09-06-osint-evidence-pipeline-v1.md`

## Global Constraints

- Humanitarian privacy is unchanged; no MMSI/IMO/callsign leakage into Humanitarian publication.
- Vessel class is context, never an allegation and never a global detector suppressor.
- Same sensor lineage cannot count as multiple independent sources.
- Unknown lineage is conservative and cannot create independent corroboration.
- No change to vessel marker rendering, Live/Play vessel identity contracts, or Drift ownership.
- No production deploy until full verification and CI/CodeQL are green.

---
### Task 1: Evidence lineage classifier

**Files:**
- Create: `apps/api/core/intel/evidence_lineage.py`
- Create: `tests/test_evidence_lineage.py`

**Interfaces:**
- Produces: `EvidenceLineage(source_name, source_family, independence_group, sensor_family)`.
- Produces: `lineage_for_event(event: IntelEvent) -> EvidenceLineage`.

- [ ] **Step 1: Write failing tests** for AISStream, internal `mda`, GFW AIS-derived events, catalogued non-AIS sources, and unknown sources. The expected contract is that AISStream, `mda`, `ais`, `AIS incidents`, and GFW all resolve to `sensor_family="ais"` and `independence_group="ais_sensor_lineage"`; GDACS keeps an independent `gdacs` group; unknown sources resolve to `independence_group="unknown"`.
- [ ] **Step 2: Run** `apps/api/.venv/bin/python -m pytest tests/test_evidence_lineage.py -q` and verify RED because the module does not exist.
- [ ] **Step 3: Implement minimal classifier** using `core.intel.source_catalog.get_source_profile()`, explicit internal AIS aliases, and a conservative unknown fallback. Do not add provider reliability scoring.
- [ ] **Step 4: Re-run the focused tests** and verify GREEN.
- [ ] **Step 5: Commit** `feat: add evidence lineage classifier`.

### Task 2: Verification semantics from lineage

**Files:**
- Modify: `apps/api/core/intel/fusion.py`
- Modify: `tests/test_fusion.py`

**Interfaces:**
- `FusionSignal` gains `source_family`, `independence_group`, and `sensor_family`.
- Add pure helper `verification_for_event_ids(event_ids: list[str]) -> tuple[str, list[str], int]` returning `(verification_status, independence_groups, evidence_count)`.

- [ ] **Step 1: Add failing fusion tests** proving one event -> `single_source_observed`, two distinct AIS anomaly events from AISStream/MDA -> `single_source_multi_indicator`, and AIS + GDACS/other independent source -> `multi_source_corroborated`.
- [ ] **Step 2: Run the focused tests** and verify they fail against the current unconditional `multi_source_corroborated` emission.
- [ ] **Step 3: Implement minimal lineage fields and verification helper.** `_emit_locked()` must persist `verification_status`, `contributing_independence_groups`, `independent_source_count`, and `evidence_count` from actual contributors; never infer corroboration from detector count alone.
- [ ] **Step 4: Re-run `tests/test_fusion.py`** and keep existing compatible alert creation green except tests intentionally changed by Task 3.
- [ ] **Step 5: Commit** `fix: derive fusion verification from source lineage`.
### Task 3: Same-lineage episode and case gate

**Files:**
- Modify: `apps/api/core/intel/fusion.py`
- Modify: `apps/api/core/live/projection.py`
- Modify: `tests/test_fusion.py`
- Modify: relevant Live/public projection test file found during implementation

**Interfaces:**
- Add helper `has_independent_corroboration(event_ids: list[str]) -> bool` backed by Task 2 verification.
- Same-lineage fused records remain `correlated_alert` for compatibility but carry `publication_status="internal"` and `open_case=False` for grey-zone/sanctions hypotheses that lack independent corroboration.

- [ ] **Step 1: Write failing tests** changing the current spoofing and infrastructure expectations: two AIS anomalies on one lineage may emit one `single_source_multi_indicator` alert but must not create a CaseDB row; infra-proximity + gap on the same MMSI and same AIS lineage must not open a `subsea_infrastructure` case.
- [ ] **Step 2: Add a failing public-projection test** proving a `correlated_alert` marked `single_source_multi_indicator` + `publication_status=internal` is not exposed in security/grey-zone public projection.
- [ ] **Step 3: Run focused tests and verify RED.**
- [ ] **Step 4: Implement the minimal gate** in `_rule_spoofing`, `_rule_grey_zone`, and emission/public projection. High-specificity sanctions identity matches are not globally disabled; only same-lineage multi-indicator promotion is blocked.
- [ ] **Step 5: Re-run focused tests and verify GREEN.**
- [ ] **Step 6: Commit** `fix: keep same-lineage maritime indicators internal`.

### Task 4: YOUR WISDOM regression fixture and operator wording

**Files:**
- Create: `tests/fixtures/osint/benign_service_vessels.jsonl`
- Modify: `tests/test_fusion.py` or create `tests/test_osint_evidence_regressions.py`
- Modify: `apps/web/src/features/intel/categories.js`
- Modify: `prompt.md`
- Modify: `docs/current_work.md`

**Interfaces:**
- Fixture row includes vessel identity/context and two same-lineage observations.
- Regression assertion: no intelligence CaseDB row, verification is not `multi_source_corroborated`, and any fused compatibility record is internal.

- [ ] **Step 1: Write the fixture and failing regression test** for YOUR WISDOM (MMSI 229113000, IMO 9848388, high-speed passenger ferry, Malta/Gozo service context) using synthetic observation timestamps/geometry rather than copying production rows.
- [ ] **Step 2: Run the fixture test and verify RED before any fixture-specific production change.** If Tasks 1-3 already make it GREEN, tighten the test to assert the missing explicit evidence-lineage metadata rather than adding a vessel-name suppressor.
- [ ] **Step 3: Make only generic pipeline changes needed by the fixture.** Do not hard-code YOUR WISDOM or suppress all ferries.
- [ ] **Step 4: Replace the web category claim `Multiple independent sources agree...` with evidence-neutral wording that tells the operator to inspect verification/source lineage.
- [ ] **Step 5: Update `prompt.md` and `docs/current_work.md` so OSINT Evidence Pipeline v1 precedes Review v0 and documents the new invariant.
- [ ] **Step 6: Run fixture + fusion + publication tests and commit** `test: add benign service vessel OSINT regression`.
### Task 5: Full verification and PR gate

**Files:** no new production files unless verification exposes a regression.

- [ ] **Step 1: Run full backend** with `/home/ubuntu/seacommons/apps/api/.venv/bin/python -m pytest -q` from the worktree root.
- [ ] **Step 2: Run critical Ruff/mypy gates** using the repository CI commands.
- [ ] **Step 3: Run web regression suites** for Live, Play, map, API and simulation; run web lint and unified build.
- [ ] **Step 4: Run focused vessel-marker tests** and confirm no marker assets/contracts changed.
- [ ] **Step 5: Run edge tests/dry-run if proxy/public projection files changed.**
- [ ] **Step 6: `git diff --check`, inspect exact diff, and run the verification-before-completion checklist.
- [ ] **Step 7: Push branch, open PR, wait for Full CI + CodeQL, and only then merge/deploy after exact-head verification.

## Self-review

Spec coverage: Tasks 1-4 cover lineage, verification vocabulary, same-lineage case/publication gates, YOUR WISDOM regression, and operator wording. Task 5 covers deployment gates. No Review v0 implementation is mixed into this packet.

Placeholder scan: no TODO/TBD implementation gaps are permitted. Any newly discovered uncertainty must be documented as a deferred packet instead of silently guessed.

Type consistency: `EvidenceLineage.independence_group` is the single fusion corroboration key; `verification_for_event_ids()` is the only helper allowed to assign the three v1 fusion verification states.