# Current work — Evidence Fusion Development Loop

> **Canonical loop:** `docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md`
> **Current packet:** Cross-modal Evidence Fusion v1 — Task 2 Humanitarian resolution context bridge
> **Current packet plan:** `docs/superpowers/plans/2026-09-06-cross-modal-evidence-fusion-v1.md`
> **Production runtime baseline:** `0ae4df7cc20c8209acc267eb595129c2dc3961bd`
> **Production schema:** `0021_maritime_episodes`

## Production baseline

OSINT Evidence Pipeline v1, Vessel Context + Behavioural Baseline v1, and Observation -> Episode -> Hypothesis v1 are merged, deployed and production-verified. Production keeps the Humanitarian privacy boundary, shared Live/Play vessel-marker contract, and evidence-lineage semantics where detector/provider multiplicity is not source independence.

Evidence Fusion development remains isolated from production. No development packet below implies a deploy, migration, restart, AIS fused cutover, Humanitarian auto-resolution, or remote-radio activation.

## Completed development packets

### Free/Open AIS Fusion v1

Development-complete and shadow-ready. It adds the compatibility-preserving AIS event bus, normalized provider/health contract, AISStream + Open Waters/aiscast adapters, conservative reconciliation, coverage-aware gap reasoning, reconciled SAR context, bounded observability, and `legacy | shadow | fused` runtime modes. Runtime remains `legacy` unless an operator explicitly authorizes a cutover.

### Humanitarian Verification v1

Development-complete and review-ready through `961c436`. Alarm Phone aliases resolve to one `operational_origin` identity; operational SAR NGOs resolve to `verification`; IOM Missing Migrants remains `archive_reference`. Real monitored NGO X handles normalize to their canonical source identities before transport reasoning.

Verification sources extract deterministic claims, associate only on strong multi-feature matching, and update replayable `sar_mission` / `resolution` assessments without creating another Humanitarian incident or mutating canonical lifecycle. AIS alone cannot confirm rescue. Verification events with no deterministic Humanitarian claim do not create correlation noise. Operator summaries and metrics preserve the Humanitarian privacy boundary.

Release evidence: focused privacy/lineage `141 passed`; full backend `1350 passed, 2 skipped`; Ruff/mypy/migrations/Python dependency audit green; web test/lint/typecheck/build/audit green; edge `12 passed`, Wrangler dry-run and audit green.

## Completed packet — Remote Maritime Radio v1

Development-complete / review-ready through `2ea9e35`. Provider-neutral contracts, explicit bounded receiver registry, KiwiSDR/OpenWebRX adapters, canonical SourceObservation persistence, disabled-by-default runtime, bounded health/metrics, and operator-safe status are implemented. Physical receiver lineage is authoritative for evidence source identity; frontend/provider multiplicity cannot inflate independence. No continuous audio/IQ is persisted.

Release evidence: focused radio/privacy/lineage `82 passed`; full backend `1385 passed, 2 skipped`; Ruff/mypy/migrations/canonical project dependency audit green; web/edge gates green. Production receiver activation remains separate and unauthorized.

## Completed packet — DSC + NAVTEX Structured Evidence v1

Development-complete / review-ready through `08c20f4`. Already-decoded DSC/NAVTEX inputs normalize into immutable structured observations keyed to physical receiver lineage. DSC distress may project only a Maritime Safety candidate; NAVTEX remains context-only. No waveform/audio/IQ is persisted, and no signal type creates or resolves Humanitarian state.

Release evidence: focused `116 passed`; full backend `1424 passed, 2 skipped`; Ruff/mypy/migrations/canonical dependency audit green. Structured runtime remains disabled by default and production activation is separate.

## Completed packet — Audio Evidence v1

Development-complete / review-ready through `1271a85`. Immutable bounded audio artifact metadata, migration `0022_audio_artifacts`, disabled-by-default acquisition policy, and derived-only transcript contracts are implemented. Production capture remains unauthorized.

Release evidence: focused audio/privacy/provenance `80 passed`; full backend `1458 passed, 2 skipped`; Ruff/mypy/migrations/canonical dependency audit green.

## Current packet state — Cross-modal Evidence Fusion v1

Packet E introduces bounded, legally-permitted audio evidence artifacts with explicit content hash, receiver/frequency/time provenance and retention policy. Audio is evidence storage, not a truth store: transcript/claim extraction remains derived and cannot directly mutate Humanitarian lifecycle or public allegations. Task 0 defines the immutable artifact contract and fail-closed retention/terms boundary before any acquisition runtime exists.

## Loop order

1. Remote Maritime Radio v1 — software-only receiver abstraction, identity/capability/health, KiwiSDR/OpenWebRX adapters, bounded observations.
2. DSC + NAVTEX structured evidence.
3. Audio Evidence v1 — immutable bounded audio artifacts with explicit retention; transcription remains derived evidence.
4. Cross-modal Evidence Fusion v1 — combine Humanitarian, AIS and radio while preserving lineage independence.
5. Review v0 / publication controls on top of real evidence workflows.

## Core domain rules

Alarm Phone is currently the Humanitarian incident-creation authority, not the only Humanitarian source. Source identity is resolved before transport lineage: two distinct first-party organizations can remain independent even when both publish through X, while two transports/frontends for the same organization or physical receiver do not multiply evidence.

NGO AIS behaviour may establish `response_detected` or `rescue_activity_probable`, but AIS alone never confirms rescue. Explicit first-party rescue claims can contribute to `rescue_confirmed` only after strong association with the Alarm Phone incident; ambiguous matches require review.

Radio/audio follows the same model: adapters produce observations/artifacts; source/receiver identity and physical lineage are preserved; derived decodes/transcripts/claims cannot silently mutate canonical lifecycle.

## Execution discipline

TDD RED -> GREEN for every behavior change, one semantic commit per task, focused regression gate before advancing, full release gate at packet completion, and exact diff review before merge readiness. Production deploy/migration/restart remains separately controlled.
