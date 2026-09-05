# Play / Live Shared Public Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Play visually identical to public Live while keeping Play temporal/archive semantics, a satellite-first default map, and a fail-safe non-blank canvas.

**Architecture:** Play will reuse Live's public shell class system and map controls instead of maintaining a parallel visual design. Play-specific archive, timeline, satellite evidence, and dossier logic remain isolated, while map initialization is made deterministic and independent of incident selection.

**Tech Stack:** React, MapLibre GL JS, Vite, Node test runner, CSS, Playwright used ephemerally for visual smoke only.

**Spec:** `docs/superpowers/specs/2026-09-05-play-live-shared-shell-design.md`

## Global Constraints

- Play opens in `ALL` with VIIRS true-colour satellite imagery as the default basemap.
- OSM stays underneath only as a fallback and must never visually dominate a healthy satellite layer.
- Public Live and Play hide the persistent attribution control; provider attribution remains in source metadata/docs.
- Vessel identities use the Live triangle convention; non-vessel incidents remain incident markers.
- Mobile selected-case layout is map-top + full-width report-bottom.
- No Cesium or Unreal dependency may enter the public Play bundle.
- Deployment requires green local gates, screenshots, Full CI, CodeQL, and public post-deploy visual smoke.

---### Task 1: Deterministic satellite-first Play map

**Files:**
- Modify: `apps/web/src/features/play/timeline.js`
- Modify: `apps/web/src/features/play/PlayTimeline.jsx`
- Test: `apps/web/src/features/play/timeline.test.js`

**Interfaces:**
- Consumes: `playMapStyle(day)` and current Play incident collection.
- Produces: a style whose layer order is OSM fallback → VIIRS satellite → incidents/evidence, with attribution metadata but no public attribution control.

- [ ] Add a failing test asserting the first two raster layers are fallback OSM then visible VIIRS, and that VIIRS opacity is effectively the default visual surface.
- [ ] Add a failing structural test asserting Play creates MapLibre with `attributionControl: false` and initializes incident/evidence sources on map load without requiring `selectedId`.
- [ ] Run `npm run test:play` and verify RED.
- [ ] Implement the minimal map/style fixes, including an explicit map resize after load and after first incident page hydration.
- [ ] Run `npm run test:play` and verify GREEN.
- [ ] Commit the map fix.

### Task 2: Reuse the public Live shell language

**Files:**
- Modify: `apps/web/src/play.jsx`
- Modify: `apps/web/src/features/play/PlayTimeline.jsx`
- Modify: `apps/web/src/features/play/play.css`
- Modify: `apps/web/src/styles.css` only for shared public attribution/mobile primitives when required.
- Test: `apps/web/src/features/play/timeline.test.js`
- Test: `apps/web/src/features/live/publicSurface.test.js`

**Interfaces:**
- Consumes: Live classes/tokens (`cop-shell`, `sidebar`, `sidebar-header`, `sidebar-inner`, panel/card/button tokens).
- Produces: Play shell markup using the same public Live primitives; Play-only timeline and archive controls layer onto those primitives.

- [ ] Add failing tests for the shared Live shell classes and absence of the old standalone white archive rail contract.
- [ ] Add a failing Live test asserting public attribution controls are hidden without removing source attribution strings.
- [ ] Run Play + Live tests and verify RED.
- [ ] Refactor Play markup/CSS to use the Live shell primitives and identical panel/card/button treatment.
- [ ] Keep Play filters as `ALL / HUMANITARIAN / MARITIME / CORRELATED / SATELLITE` and timeline at the bottom.
- [ ] Run Play + Live tests and verify GREEN.
- [ ] Commit the shared-shell refactor.### Task 3: Play archive filters and mobile dossier parity

**Files:**
- Modify: `apps/web/src/features/play/PlayTimeline.jsx`
- Modify: `apps/web/src/features/play/play.css`
- Test: `apps/web/src/features/play/timeline.test.js`

**Interfaces:**
- Consumes: archive incidents, `domain`, correlation/satellite evidence, global timeline state.
- Produces: Live-style filter chips and mobile map-top/report-bottom interaction.

- [ ] Add failing tests for Play filter semantics and mobile selected-case layout contract.
- [ ] Run `npm run test:play` and verify RED.
- [ ] Implement filters without changing API pagination or archive totals.
- [ ] Make selected-case mobile map retain the selected point above the report using the same padding concept as Live.
- [ ] Run `npm run test:play` and verify GREEN.
- [ ] Commit the interaction changes.

### Task 4: Candidate visual verification

**Files:**
- Create (temporary, not committed): `/tmp/seacommons-visual/playwright-smoke.mjs`
- Output (temporary): `/tmp/seacommons-visual/*.png`

**Interfaces:**
- Consumes: local Vite candidate build/preview.
- Produces: six visual acceptance screenshots.

- [ ] Run `npm run lint`, `npm run typecheck`, all web tests, and `npm run build:unified`.
- [ ] Run `git diff --check` and grep Play build artifacts for `Cesium|UnrealPixel`.
- [ ] Install/use Playwright Chromium ephemerally under `/tmp` only; do not add it to project dependencies.
- [ ] Capture Play desktop ALL, Play desktop selected case, Play mobile ALL, Play mobile selected case, Live desktop, and Live mobile selected case.
- [ ] Inspect screenshot dimensions/content and reject blank-map or clipped-panel output.
- [ ] Commit any screenshot-driven fixes, then rerun all gates if source changes.

### Task 5: PR, CI, deploy and public visual smoke

**Files:** no additional product files expected.

- [ ] Push branch and open PR against `main`.
- [ ] Wait for Full CI and CodeQL; inspect review threads and fix any valid findings.
- [ ] Merge only the exact green head SHA.
- [ ] Verify Vercel serves new Live and Play assets.
- [ ] Capture fresh public desktop/mobile screenshots for Live and Play with the same ephemeral browser harness.
- [ ] Verify satellite imagery is the default Play visual surface, archive points are visible, panels match Live, attribution box is absent, and mobile reports are not clipped.
- [ ] Report exact merge SHA, public asset hashes, and screenshot evidence.