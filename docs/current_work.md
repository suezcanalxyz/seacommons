# Current work — Evidence Fusion Development Loop

> **Canonical loop:** `docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md`
> **Current packet:** Remote Maritime Radio v1 — Task 0 provider-neutral receiver contract
> **Current packet plan:** `docs/superpowers/plans/2026-09-06-remote-maritime-radio-v1.md`
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

## Current packet state — Remote Maritime Radio v1

The next packet is software-only remote receiver acquisition. Its plan is `docs/superpowers/plans/2026-09-06-remote-maritime-radio-v1.md`. Task 0 creates the provider-neutral `RemoteReceiverAdapter`, receiver health/capability contract, and bounded `RadioObservation` metadata.

The existing `core.sensors.sdr.SDRScanner` is a local RTL-SDR anomaly scanner and is not the architecture for this packet. Remote radio must preserve provider/frontend identity separately from physical receiver/RF lineage; duplicate frontends cannot become independent evidence. No continuous audio/IQ persistence and no DSC/NAVTEX decoding belong in this packet. Runtime defaults disabled.

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
