# Production Browser & Release Qualification v1 — Design

**Date:** 2026-09-08
**Status:** design approved in chat; implementation pending written-spec review
**Scope:** frontend/browser verification only. No backend authority, schema, collector, radio, AIS, Humanitarian lifecycle, or publication-policy changes.

## Goal

Add a permanent browser-level release gate that verifies SeaCommons public Live and Play behaviour in Chromium, while keeping production smoke read-only and non-flaky.

The packet closes the documented gap that current frontend tests validate domain/services but do not exercise a real browser/runtime composition.

## Architecture

Use two deliberately separate layers:

1. **Deterministic CI E2E** — Playwright launches the built/dev Vite frontend and intercepts only public API requests with bounded canonical fixtures. This suite is blocking in CI.
2. **Read-only production smoke** — the same browser harness targets deployed public hosts without mocks. It checks availability and public contracts but never writes, authenticates, mutates lifecycle, or depends on a receiver being online.

The deterministic layer proves application behaviour. The production layer proves deployment wiring. A production outage or receiver fluctuation must not make ordinary pull-request CI red.

## Deterministic browser suite

Add `@playwright/test` as a web development dependency and a root web `playwright.config.*` configured for Chromium only.

Tests live under `apps/web/e2e/` and use stable public-safe fixtures for:

- Live Humanitarian and Maritime event projections.
- Maritime Safety examples: Aground, Not Under Command, Restricted Manoeuvrability.
- Unified acquisition status with exactly the canonical families `ais`, `first_party`, `partner`, `public_feed`, and `radio`.
- Receiver catalog/mesh rows with both `listen_available=true` and false cases.
- Play historical incident/timeline responses.

Fixture interception is limited to the HTTP endpoints required by each scenario. Asset, module, map-shell, and browser execution remain real.

No fixture may contain restricted Humanitarian identifiers, private raw source text, credentials, receiver endpoints, or invented production claims.

## Required deterministic scenarios

The blocking Chromium suite must prove:

- Live loads without uncaught page errors or console errors from SeaCommons application code.
- Humanitarian and Maritime are the canonical public signal compartments.
- Aground / NUC / Restricted Manoeuvrability render as Maritime Safety, never Humanitarian.
- Unified acquisition exposes the five canonical families and bounded health only.
- Receiver status represents `live`, `degraded`, or `offline` truthfully; Listen UI appears only when `listen_available` is true.
- A Humanitarian surface does not render MMSI, IMO, callsign, tracker dossier data, or physical receiver lineage from the supplied contract.
- Play loads the historical surface and renders a deterministic incident/timeline fixture.

Listen audio itself is not synthesized as evidence. Deterministic browser coverage may intercept the ephemeral PCM endpoint only to verify UI start/stop and header handling; fixture bytes are explicitly test data and never treated as a real radio observation.

## Production smoke

Production smoke targets the deployed public hosts and performs only GET/navigation operations.

It must verify:

- `live.seacommons.org` and `play.seacommons.org` load successfully in Chromium.
- The deployed Live page exposes the canonical Humanitarian/Maritime structure.
- Public acquisition status responds with the canonical family set and bounded metadata.
- Public pages do not produce fatal application errors.
- If a real receiver reports `listen_available=true`, the smoke may request a short ephemeral Listen stream and validate `pcm_s16le`, `no-store`, and `persistent=false` headers. If no eligible receiver exists, that check is skipped rather than failed.

Production smoke is intentionally not part of ordinary PR CI. It is invoked explicitly after deployment/release qualification and records the tested public host plus release SHA when available.

## CI and scripts

Add web scripts with distinct intent:

- `test:e2e` — deterministic Chromium suite; blocking.
- `test:e2e:production` — read-only deployed-host smoke; explicit/manual.

GitHub CI gets a dedicated browser job after `npm ci` that installs only the Chromium Playwright browser/runtime needed for the suite, builds or serves the web app, then runs `npm run test:e2e`.

The existing unit/service `npm test`, lint/typecheck, build, dependency audit, backend, and edge gates remain unchanged and continue to run independently.

Playwright traces/screenshots are retained only on failure through CI artifacts. They must not include credentials or restricted/private API payloads because the suite uses public fixtures and public hosts only.

## Failure handling and anti-flake rules

- Deterministic E2E fails on uncaught page errors, unexpected application console errors, missing canonical controls, wrong domain classification, or privacy-contract regressions.
- Tests wait on explicit application/network conditions rather than arbitrary sleeps.
- External map tiles, weather, receiver availability, and third-party services are not success criteria for deterministic CI.
- Production smoke uses bounded navigation/request timeouts and reports unavailable external dependencies as deployment evidence rather than rewriting fixture expectations.
- No retry may turn a deterministic assertion failure into green. Playwright retries, if enabled in CI, are limited to infrastructure/browser-start failures and the first failure remains visible in artifacts.

## Out of scope

This packet does not centralize outbound HTTP calls, add SSRF controls, change collectors, introduce a new publication path, activate Audio Evidence persistence, change AIS mode, or alter radio receiver authorization/failover policy.

The outbound HTTP/SSRF consolidation remains a separate security-hardening packet because it crosses multiple backend integrations and trust boundaries.

## Exit gate

Packet I is complete only when all applicable evidence is green on one exact commit:

- A RED browser test existed before each behaviour implementation.
- Deterministic Chromium E2E passes locally and in GitHub CI.
- Existing web unit/service tests, lint/typecheck, build, and dependency audit remain green.
- Backend/publication/privacy and edge suites required by touched contracts remain green; if no backend/edge contract changes occur, focused regression evidence is sufficient plus existing Full CI.
- Production read-only smoke passes against deployed Live and Play, with any unavailable optional receiver check explicitly skipped.
- No Humanitarian identifier/privacy regression is observed in browser fixtures or production public surfaces.
- `git diff --check` and exact-diff review are clean.
- Controllers record the exact implementation SHA, CI result, production smoke result, and known limitations.

## Operational constraint

The deterministic suite must remain fast enough to be a normal blocking PR gate. Browser scenarios should therefore cover high-risk cross-layer contracts, not duplicate every unit test. Additional browsers, accessibility sweeps, visual-regression baselines, and mobile matrices are future packets unless a failure found here proves they are necessary for this release gate.
