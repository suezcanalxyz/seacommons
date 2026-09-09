# Current work — Evidence Fusion Development Loop

> **Canonical loop:** `docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md`
> **Current packet:** Packet J — Outbound HTTP / SSRF Hardening v1 — implementation active; production qualification pending
> **Active packet plan:** `docs/superpowers/plans/2026-09-09-outbound-http-ssrf-hardening-v1.md`
> **Release-qualified main:** `908dc81`
> **Production behavior baseline:** `f9ceb46`
> **Production schema:** `0026_radio_ais_associations`

## Production baseline

Packets H and I are accepted and production-verified. Release-qualified `main` is `908dc81`; the latest production behavior change is `f9ceb46`. Public Live uses the canonical Humanitarian/Maritime split and `/api/v1/live/pipeline` reports the bounded acquisition families `ais`, `first_party`, `partner`, `public_feed`, and `radio`. The AIS runtime remains in the authorized legacy mode; raw AIS context layers are default-off on public Live and remain user-toggleable.

The Mediterranean radio mesh is live with ephemeral Listen Live audio and managed receiver coverage/failover. The production policy is reconnect-before-failover for transient receiver drops, three desired independent active lineages for the monitored channel when capacity exists, and ranked standby promotion only when reconnect/staleness rules require it. Audio Evidence persistence remains disabled (`AUDIO_EVIDENCE_ENABLED=false`); Listen Live is ephemeral PCM with `no-store` and no persistent audio body.

Final Packet H evidence on the current production line: full backend `1632 passed, 2 skipped`; focused H backend `110 passed`; Live web `65 passed`; Full CI and CodeQL green on `b358dec`; Vercel production READY; Alembic `0026_radio_ais_associations (head)`. Publication/privacy gates remain fail-closed and physical receiver lineage remains the radio independence boundary.

## Completed development packets

### Free/Open AIS Fusion v1

Development-complete and shadow-ready. It adds the compatibility-preserving AIS event bus, normalized provider/health contract, AISStream + Open Waters/aiscast adapters, conservative reconciliation, coverage-aware gap reasoning, reconciled SAR context, bounded observability, and `legacy | shadow | fused` runtime modes. Runtime remains `legacy` unless an operator explicitly authorizes a cutover.

### Humanitarian Verification v1

Development-complete and review-ready through `961c436`. Alarm Phone aliases resolve to one `operational_origin` identity; operational SAR NGOs resolve to `verification`; IOM Missing Migrants remains `archive_reference`. Real monitored NGO X handles normalize to their canonical source identities before transport reasoning.

Verification sources extract deterministic claims, associate only on strong multi-feature matching, and update replayable `sar_mission` / `resolution` assessments without creating another Humanitarian incident or mutating canonical lifecycle. AIS alone cannot confirm rescue. Verification events with no deterministic Humanitarian claim do not create correlation noise. Operator summaries and metrics preserve the Humanitarian privacy boundary.

Release evidence: focused privacy/lineage `141 passed`; full backend `1350 passed, 2 skipped`; Ruff/mypy/migrations/Python dependency audit green; web test/lint/typecheck/build/audit green; edge `12 passed`, Wrangler dry-run and audit green.

## Completed packet — Remote Maritime Radio v1

Development-complete / review-ready through `6a4f885`. Provider-neutral contracts, explicit bounded receiver registry, KiwiSDR/OpenWebRX adapters, canonical SourceObservation persistence, disabled-by-default runtime, bounded health/metrics, and operator-safe status are implemented. Physical receiver lineage is authoritative for evidence source identity; frontend/provider multiplicity cannot inflate independence. No continuous audio/IQ is persisted.

Release evidence: focused radio/privacy/lineage `82 passed`; full backend `1385 passed, 2 skipped`; Ruff/mypy/migrations/canonical project dependency audit green; web/edge gates green. Production receiver activation remains separate and unauthorized.

## Completed packet — DSC + NAVTEX Structured Evidence v1

Development-complete / review-ready through `f09afcb`. Already-decoded DSC/NAVTEX inputs normalize into immutable structured observations keyed to physical receiver lineage. DSC distress may project only a Maritime Safety candidate; NAVTEX remains context-only. No waveform/audio/IQ is persisted, and no signal type creates or resolves Humanitarian state.

Release evidence: focused `116 passed`; full backend `1424 passed, 2 skipped`; Ruff/mypy/migrations/canonical dependency audit green. Structured runtime remains disabled by default and production activation is separate.

## Completed packet — Audio Evidence v1

Development-complete / review-ready through `90d08e4`. Immutable bounded audio artifact metadata, migration `0022_audio_artifacts`, disabled-by-default acquisition policy, and derived-only transcript contracts are implemented. Production capture remains unauthorized.

Release evidence: focused audio/privacy/provenance `80 passed`; full backend `1458 passed, 2 skipped`; Ruff/mypy/migrations/canonical dependency audit green.

## Completed packet — Cross-modal Evidence Fusion v1

Development-complete / review-ready through `52efdd1`. Evidence packets preserve source lineage and modality; AIS provider multiplicity collapses to one AIS modality; derived AIS/audio evidence never adds independence. Contradictions remain explicit records rather than confidence averages. Humanitarian ResolutionAssessment and MaritimeEpisode receive bounded context only, with no lifecycle/publication/hypothesis-state mutation and no receiver/MMSI leakage.

Release evidence: focused privacy/lineage `108 passed`; full backend `1483 passed, 2 skipped`; Ruff/mypy/migrations/dependency audit green; web/edge gates green.

## Completed packet — Review v0 / publication controls

Development-complete / review-ready through code HEAD `19dbb7d`. ReviewRecord is immutable and replay-deterministic; migration `0023_review_records` adds the append-only ledger; Humanitarian approvals create audited incident transitions, while Maritime approvals delegate to the existing hypothesis state machine. `published` is not a ReviewRecord transition and all publication remains behind existing domain-specific gates.

Release evidence: focused review/privacy/publication `181 passed`; full backend `1519 passed, 2 skipped`; Ruff/mypy/migrations through `0023`/dependency audit green; web and edge gates green. Exact-diff review fixes are included.

## Current execution packet

Packet J — **Outbound HTTP / SSRF Hardening v1** — is the active implementation packet. Its approved design/spec introduces `PUBLIC_UNTRUSTED`, `PUBLIC_FIXED`, and `OPERATOR_INTERNAL`, pinned DNS/IP connections, manual redirect validation, bounded response contracts, redacted failures, and bounded outbound metrics. Tasks 1–6 are implemented on `feat/outbound-http-ssrf-hardening-v1`; Task 7 release qualification is in progress.

The v1 high-risk migrations cover untrusted image extraction, X/Twitter media, auto-drift, remote drift worker, OIDC/JWKS, and forensic witnesses. The post-migration legacy inventory currently contains 29 exact path/callee entries representing 44 direct HTTP calls, primarily fixed collectors/integrations to be migrated in later bounded batches. New direct bypasses are blocked by an AST inventory guard; WebSocket URL policy remains explicitly out of scope for Packet J v1.

Packet I — **Production Browser & Release Qualification v1** — is accepted/closed. PR #155 merged the deterministic Chromium gate and read-only production-smoke path; PR #156 fixed AIS distress beacons that were incorrectly falling through to `context`; PR #157 made manual release qualification skip only the redundant full-history gitleaks step while preserving gitleaks on PR/push. Release-qualified `main` is `908dc81`; the runtime behavior change is `f9ceb46`.

Final Packet I evidence: deterministic `browser-e2e` PASS; production `browser-production-smoke` PASS against the real `live.seacommons.org` and `play.seacommons.org` hosts with no route mocks; manual Full CI run `34258991088` completed SUCCESS with `repository`, `api`, `web`, `edge`, `browser-e2e`, and `browser-production-smoke` all green. The production API returned Maritime Safety casualties as canonical `navigation_casualty / #ff4d5e` and AIS distress beacons as `distress / #ff3b3b`.

The Packet I browser pass fixed the public Live regression visible in production: raw AIS moving/stationary/trails start off under a versioned incident-first public layer profile while remaining user-toggleable; Alarm Phone is categorized by semantic role rather than raw `twitter` transport type; and Maritime Safety fusion alerts calculate/render canonical semantic colour from enriched public metadata. No publication, retention or source eligibility rule changed.

Packet J is authorized and in execution. Do not expand v1 into wholesale migration of all fixed collectors or WebSocket transports; those remain follow-up batches after the canonical HTTP trust boundary is production-qualified.

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
